"""
Tests for the SEC requests in src/fundamentals.py. No network: requests.get is
replaced by a stand-in that records how it was called.
"""
import pytest
import requests

import src.fundamentals as fundamentals


class _Response:
    def __init__(self, status_code, payload):
        self.status_code, self._payload = status_code, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._payload


def _fake_get(status_code, payload, calls):
    def fake(url, headers=None, timeout=None):
        calls.append({"url": url, "timeout": timeout})
        return _Response(status_code, payload)
    return fake


def test_company_facts_request_has_a_timeout_and_returns_the_json(monkeypatch):
    calls = []
    monkeypatch.setattr(fundamentals, "get_cik", lambda ticker: "0000000001")
    monkeypatch.setattr(fundamentals.requests, "get", _fake_get(200, {"facts": {}}, calls))
    assert fundamentals.get_company_facts("TEST") == {"facts": {}}
    assert calls[0]["timeout"] == fundamentals.REQUEST_TIMEOUT_SECONDS
    assert calls[0]["url"].endswith("CIK0000000001.json")


def test_an_error_page_from_the_sec_stops_the_run_instead_of_being_read_as_data(monkeypatch):
    """A 429 (too many requests) or 403 answer is not a company's facts. It must raise."""
    monkeypatch.setattr(fundamentals, "get_cik", lambda ticker: "0000000001")
    monkeypatch.setattr(fundamentals.requests, "get", _fake_get(429, {"message": "slow down"}, []))
    with pytest.raises(requests.HTTPError):
        fundamentals.get_company_facts("TEST")


def test_ticker_map_request_has_a_timeout_and_stops_on_an_error_page(monkeypatch):
    calls = []
    monkeypatch.setattr(fundamentals, "_TICKER_CIK_MAP", None)
    monkeypatch.setattr(fundamentals.requests, "get", _fake_get(403, {}, calls))
    with pytest.raises(requests.HTTPError):
        fundamentals.get_cik("TEST")
    assert calls[0]["timeout"] == fundamentals.REQUEST_TIMEOUT_SECONDS
    assert fundamentals._TICKER_CIK_MAP is None       # nothing half-loaded is kept for the next call
