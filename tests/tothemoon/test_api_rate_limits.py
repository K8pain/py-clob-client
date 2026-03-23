import httpx

from ToTheMoon.api import EndpointRateLimiter, PolymarketHttpClient, RateLimitPolicy
from ToTheMoon.strategies.polymarket_engine.discovery import GammaDiscoveryClient
from ToTheMoon.strategies.polymarket_engine.execution import RealExecutionAdapter
from ToTheMoon.strategies.polymarket_engine.models import OrderRequest, OrderSide


def test_endpoint_rate_limiter_waits_when_window_is_full():
    timestamps = iter([0.0, 0.0, 0.1, 1.0])
    sleeps: list[float] = []
    limiter = EndpointRateLimiter(
        RateLimitPolicy("test", 1, 1.0),
        clock=lambda: next(timestamps),
        sleeper=lambda seconds: sleeps.append(seconds),
    )

    limiter.acquire()
    limiter.acquire()

    assert sleeps == [0.9]


def test_http_client_retries_after_429():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as raw_client:
        client = PolymarketHttpClient(client=raw_client)
        client.register_limit(RateLimitPolicy("gamma-markets", 250, 10.0))
        response = client.get("https://gamma-api.polymarket.com/markets", policy_name="gamma-markets")

    assert response.json() == {"ok": True}
    assert attempts["count"] == 2


def test_gamma_discovery_client_uses_rate_limited_http_client():
    class StubHttpClient:
        def __init__(self):
            self.calls = []
            self.policies = []

        def register_limit(self, policy):
            self.policies.append(policy)

        def get(self, url, policy_name=None):
            self.calls.append((url, policy_name))

            class Response:
                def json(self_nonlocal):
                    return [{"id": "m1", "event_id": "e1", "market_slug": "slug", "tokens": []}]

            return Response()

    stub = StubHttpClient()
    client = GammaDiscoveryClient("https://gamma-api.polymarket.com", http_client=stub)
    client.fetch_markets()

    assert stub.policies[0].name == "gamma-markets"
    assert stub.calls == [("https://gamma-api.polymarket.com/markets", "gamma-markets")]


def test_real_execution_adapter_acquires_rate_limiter():
    class StubLimiter:
        def __init__(self):
            self.calls = 0

        def acquire(self):
            self.calls += 1

    limiter = StubLimiter()
    adapter = RealExecutionAdapter(client=None, rate_limiter=limiter)
    payload = adapter.execute(
        OrderRequest(
            token_id="token-1",
            side=OrderSide.BUY,
            price=0.44,
            size=3.0,
            market_id="market-1",
            strategy_name="tail",
            signal_reason="extremeness_score=0.95",
        )
    )

    assert limiter.calls == 1
    assert payload["status"] == "ready_to_submit"
