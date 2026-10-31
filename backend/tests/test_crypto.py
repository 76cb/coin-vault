import pytest


def test_round_trip_and_tamper(app, monkeypatch):
    from app import crypto
    from app.config import get_settings

    token = crypto.encrypt("sc_live_abc123")
    assert token.startswith("v1:") and "sc_live_abc123" not in token
    assert crypto.encrypt("sc_live_abc123") != token  # fresh nonce each time
    assert crypto.decrypt(token) == "sc_live_abc123"

    with pytest.raises(Exception):
        crypto.decrypt(token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB"))

    monkeypatch.setattr(get_settings(), "encryption_key", crypto.generate_key())
    with pytest.raises(Exception):
        crypto.decrypt(token)  # a different key can't read it

    for bad in ("not base64!", "c2hvcnQ="):
        monkeypatch.setattr(get_settings(), "encryption_key", bad)
        with pytest.raises(crypto.EncryptionUnavailable):
            crypto.encrypt("x")
