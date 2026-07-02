"""Unit tests — JWT issue/decode and password hashing."""
import pytest
from jose import JWTError

from src.shared.security.jwt import create_access_token, decode_token
from src.shared.security.password import hash_password, verify_password


class TestPassword:

    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("S3cret-password")
        assert hashed != "S3cret-password"
        assert verify_password("S3cret-password", hashed)

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct-password")
        assert not verify_password("wrong-password", hashed)

    def test_hashes_are_salted(self):
        assert hash_password("same") != hash_password("same")


class TestJwt:

    def _issue(self, **overrides):
        claims = {
            "sub": "11111111-1111-1111-1111-111111111111",
            "enterprise_id": "22222222-2222-2222-2222-222222222222",
            "role": "SUPER_ADMIN",
            "email": "admin@example.com",
        }
        claims.update(overrides)
        return create_access_token(claims)

    def test_access_token_roundtrip(self):
        token = self._issue()
        payload = decode_token(token)
        assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
        assert payload["role"] == "SUPER_ADMIN"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "exp" in payload

    def test_tampered_token_rejected(self):
        token = self._issue()
        with pytest.raises(JWTError):
            decode_token(token[:-4] + "XXXX")

    def test_unique_jti_per_token(self):
        assert decode_token(self._issue())["jti"] != decode_token(self._issue())["jti"]
