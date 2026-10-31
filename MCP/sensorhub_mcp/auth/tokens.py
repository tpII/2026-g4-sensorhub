"""Tokens firmados con HMAC-SHA256: el servidor no guarda los access ni los
refresh tokens, los verifica recalculando la firma. Así sobreviven a un
reinicio del contenedor sin necesidad de una base de datos ni de un volumen."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


def b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class TokenSigner:
    """Emite y verifica tokens con la forma `<payload base64url>.<firma base64url>`.

    La clave de firma se deriva del secreto y de la contraseña del usuario: al
    cambiar cualquiera de los dos, todos los tokens emitidos dejan de verificar
    y los clientes tienen que volver a pasar por el login."""

    def __init__(self, secret: str, password: str):
        self._key = hmac.new(
            secret.encode("utf-8"),
            b"sensorhub-oauth\x00" + password.encode("utf-8"),
            hashlib.sha256,
        ).digest()

    def _sign(self, payload_b64: str) -> str:
        return b64encode(hmac.new(self._key, payload_b64.encode("ascii"), hashlib.sha256).digest())

    def issue(self, token_type: str, ttl_seconds: int, **claims: Any) -> tuple[str, int]:
        """Devuelve el token y su vencimiento (epoch en segundos)."""
        expires_at = int(time.time()) + ttl_seconds
        payload = {"typ": token_type, "exp": expires_at, "jti": secrets.token_urlsafe(8), **claims}
        payload_b64 = b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        return f"{payload_b64}.{self._sign(payload_b64)}", expires_at

    def verify(self, token: str, token_type: str) -> dict[str, Any] | None:
        """Devuelve los claims si la firma es válida, el tipo coincide y no venció."""
        if not token.isascii():
            return None
        payload_b64, sep, signature = token.partition(".")
        if not sep or not hmac.compare_digest(signature, self._sign(payload_b64)):
            return None
        try:
            payload = json.loads(b64decode(payload_b64))
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("typ") != token_type:
            return None
        if not isinstance(payload.get("exp"), int) or payload["exp"] < time.time():
            return None
        return payload
