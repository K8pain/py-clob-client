from unittest.mock import Mock

import httpx

from py_clob_client.http_helpers import helpers


def test_request_retries_once_after_remote_protocol_error(monkeypatch):
    original_client = Mock()
    original_client.request.side_effect = httpx.RemoteProtocolError("goaway")

    replacement_client = Mock()
    replacement_response = Mock(status_code=200)
    replacement_response.json.return_value = {"ok": True}
    replacement_client.request.return_value = replacement_response

    client_factory = Mock(return_value=replacement_client)
    monkeypatch.setattr(helpers, "_http_client", original_client)
    monkeypatch.setattr(helpers.httpx, "Client", client_factory)

    response = helpers.request("https://example.test", helpers.GET)

    assert response == {"ok": True}
    original_client.request.assert_called_once()
    original_client.close.assert_called_once()
    client_factory.assert_called_once_with(http2=True)
    replacement_client.request.assert_called_once()


def test_request_retries_once_after_read_timeout(monkeypatch):
    original_client = Mock()
    original_client.request.side_effect = httpx.ReadTimeout("slow", request=Mock())

    replacement_client = Mock()
    replacement_response = Mock(status_code=200)
    replacement_response.json.return_value = {"ok": True}
    replacement_client.request.return_value = replacement_response

    client_factory = Mock(return_value=replacement_client)
    monkeypatch.setattr(helpers, "_http_client", original_client)
    monkeypatch.setattr(helpers.httpx, "Client", client_factory)

    response = helpers.request("https://example.test", helpers.GET)

    assert response == {"ok": True}
    original_client.request.assert_called_once()
    original_client.close.assert_called_once()
    client_factory.assert_called_once_with(http2=True)
    replacement_client.request.assert_called_once()
