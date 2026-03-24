from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

import httpx
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter


class RateLimitExceeded(RuntimeError):
    """Raised when the local limiter predicts a Polymarket quota breach."""


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: float

    @property
    def requests_per_second(self) -> float:
        return self.limit / self.window_seconds


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 5
    min_wait_seconds: float = 0.25
    max_wait_seconds: float = 4.0


def _retry_if_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code == 429 or 500 <= status_code < 600
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, RateLimitExceeded))


def _before_sleep(retry_state: RetryCallState) -> None:
    outcome = retry_state.outcome
    if outcome is None:
        return
    exception = outcome.exception()
    if exception is None:
        return
    if isinstance(exception, httpx.HTTPStatusError):
        retry_after = exception.response.headers.get("Retry-After")
        if retry_after:
            time.sleep(max(float(retry_after), 0.0))


class EndpointRateLimiter:
    def __init__(self, policy: RateLimitPolicy, *, clock: Callable[[], float] | None = None, sleeper: Callable[[float], None] | None = None) -> None:
        self.policy = policy
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._lock = Lock()
        self._window_started_at = self._clock()
        self._request_count = 0

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            elapsed = now - self._window_started_at
            if elapsed >= self.policy.window_seconds:
                self._window_started_at = now
                self._request_count = 0
                elapsed = 0.0

            if self._request_count >= self.policy.limit:
                wait_seconds = self.policy.window_seconds - elapsed
                if wait_seconds > 0:
                    self._sleep(wait_seconds)
                self._window_started_at = self._clock()
                self._request_count = 0

            self._request_count += 1


class PolymarketHttpClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_policy: RetryPolicy | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout, headers=default_headers)
        self._owns_client = client is None
        self._retry_policy = retry_policy or RetryPolicy()
        self._limiters: dict[str, EndpointRateLimiter] = {}

    def register_limit(self, policy: RateLimitPolicy) -> None:
        self._limiters[policy.name] = EndpointRateLimiter(policy)

    def get(self, url: str, *, params: dict[str, Any] | None = None, policy_name: str | None = None) -> httpx.Response:
        return self.request("GET", url, params=params, policy_name=policy_name)

    def post(self, url: str, *, json_body: Any | None = None, policy_name: str | None = None) -> httpx.Response:
        return self.request("POST", url, json=json_body, policy_name=policy_name)

    def delete(self, url: str, *, json_body: Any | None = None, policy_name: str | None = None) -> httpx.Response:
        return self.request("DELETE", url, json=json_body, policy_name=policy_name)

    def request(self, method: str, url: str, *, policy_name: str | None = None, **kwargs: Any) -> httpx.Response:
        limiter = self._limiters.get(policy_name) if policy_name else None

        @retry(
            retry=retry_if_exception(_retry_if_http_error),
            stop=stop_after_attempt(self._retry_policy.attempts),
            wait=wait_exponential_jitter(
                initial=self._retry_policy.min_wait_seconds,
                max=self._retry_policy.max_wait_seconds,
            ),
            before_sleep=_before_sleep,
            reraise=True,
        )
        def _send() -> httpx.Response:
            if limiter is not None:
                limiter.acquire()
            requester = getattr(self._client, "request", None)
            if requester is None:
                requester = getattr(self._client, method.lower())
            response = requester(method, url, **kwargs) if getattr(self._client, "request", None) is not None else requester(url, **kwargs)
            response.raise_for_status()
            return response

        return _send()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PolymarketHttpClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
