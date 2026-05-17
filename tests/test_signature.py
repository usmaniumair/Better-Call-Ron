"""Regression tests for AgentPhone webhook signature verification.

AgentPhone signs `{X-Webhook-Timestamp}.{raw body}` (Stripe-style), not just
the body. The bundled SDK's `verify_webhook` only hashes the body and so
rejects every real inbound webhook. Our `agentphone_client.verify_signature`
must implement the correct scheme.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from unittest.mock import patch

from src import agentphone_client


_SECRET = "whsec_test_secret_for_regression_only"


def _sign(timestamp: str, body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def _with_secret(fn):
    """Run a test with AGENTPHONE_WEBHOOK_SECRET temporarily set."""
    def wrapper():
        with patch.dict(os.environ, {"AGENTPHONE_WEBHOOK_SECRET": _SECRET}):
            fn()
    return wrapper


@_with_secret
def test_valid_signature_accepted():
    body = b'{"event":"agent.message","data":{}}'
    ts = "1778915134"
    assert agentphone_client.verify_signature(body, _sign(ts, body), ts) is True


@_with_secret
def test_tampered_body_rejected():
    body = b'{"event":"agent.message","data":{}}'
    ts = "1778915134"
    sig = _sign(ts, body)
    tampered = body + b" "
    assert agentphone_client.verify_signature(tampered, sig, ts) is False


@_with_secret
def test_wrong_timestamp_rejected():
    body = b'{"event":"agent.message","data":{}}'
    sig = _sign("1778915134", body)
    assert agentphone_client.verify_signature(body, sig, "1778915135") is False


@_with_secret
def test_body_only_signature_rejected():
    # Catches accidental regression to the old SDK scheme.
    body = b'{"event":"agent.message","data":{}}'
    ts = "1778915134"
    body_only_sig = "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert agentphone_client.verify_signature(body, body_only_sig, ts) is False


@_with_secret
def test_wrong_secret_rejected():
    body = b'{"event":"agent.message","data":{}}'
    ts = "1778915134"
    sig = _sign(ts, body, secret="whsec_wrong")
    assert agentphone_client.verify_signature(body, sig, ts) is False


@_with_secret
def test_missing_signature_rejected():
    body = b'{"event":"agent.message","data":{}}'
    assert agentphone_client.verify_signature(body, "", "1778915134") is False


@_with_secret
def test_missing_timestamp_rejected():
    body = b'{"event":"agent.message","data":{}}'
    sig = _sign("1778915134", body)
    assert agentphone_client.verify_signature(body, sig, "") is False


@_with_secret
def test_signature_without_prefix_rejected():
    # Defensive: hex without "sha256=" prefix should not pass.
    body = b'{"event":"agent.message","data":{}}'
    ts = "1778915134"
    full = _sign(ts, body)
    bare_hex = full.split("=", 1)[1]
    assert agentphone_client.verify_signature(body, bare_hex, ts) is False
