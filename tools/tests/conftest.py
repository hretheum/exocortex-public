import secrets

import pytest


@pytest.fixture()
def key(monkeypatch):
    k = secrets.token_hex(32)
    monkeypatch.setenv("LEAKGATE_HMAC_KEY", k)
    monkeypatch.delenv("LEAKGATE_HMAC_KEY_FILE", raising=False)
    return bytes.fromhex(k)
