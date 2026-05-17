from shared.docvalidator_common import decrypt_text, encrypt_text, has_permission, sign_token, verify_token


def test_encrypt_roundtrip() -> None:
    secret = "demo-key"
    value = "sensitive document payload"
    encrypted = encrypt_text(value, secret)
    assert encrypted != value
    assert decrypt_text(encrypted, secret) == value


def test_token_roundtrip() -> None:
    token = sign_token({"sub": "AUD-001", "role": "auditor"}, "jwt-secret", exp_minutes=5)
    payload = verify_token(token, "jwt-secret")
    assert payload is not None
    assert payload["sub"] == "AUD-001"


def test_permissions_matrix() -> None:
    assert has_permission("admin", "rule:read")
    assert has_permission("auditor", "validation:run")
    assert not has_permission("analyst", "quality:task:update")
