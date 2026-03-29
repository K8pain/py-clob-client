from typing import Any, Mapping


def validate_handler_input(payload: Mapping[str, Any]) -> None:
    if payload is None:
        raise ValueError("handler input payload is required")
    if not isinstance(payload, Mapping):
        raise TypeError("handler input payload must be a mapping")


def validate_external_response(response: Mapping[str, Any]) -> None:
    if response is None:
        raise ValueError("external response is required")
    if not isinstance(response, Mapping):
        raise TypeError("external response must be a mapping")
    if response.get("error"):
        raise ValueError("external response contains error")
