"""Registro de clientes OAuth sin estado (Dynamic Client Registration, el que
usan claude.ai o ChatGPT para darse de alta solos).

En vez de guardar los clientes registrados, el client_id que se entrega en
/register lleva adentro los datos del cliente (nombre, redirect_uris, etc.)
comprimidos y firmados; al recibirlo, se verifica la firma y se reconstruye el
cliente. Así un reinicio no hace perder ningún conector. El client_secret no
viaja en el client_id: se deriva de él con el secreto del servidor.

La firma usa solo MCP_AUTH_SECRET (no la contraseña): al cambiar la contraseña
los conectores siguen registrados y solo vuelven a pedir login. Cambiar el
secreto, en cambio, obliga a volver a crear los conectores."""

import hashlib
import hmac
import json
import logging
import zlib

from mcp.shared.auth import OAuthClientInformationFull

from .tokens import b64decode, b64encode

logger = logging.getLogger(__name__)


class ClientRegistry:
    def __init__(self, secret: str):
        self._key = hmac.new(secret.encode("utf-8"), b"sensorhub-oauth-clients", hashlib.sha256).digest()

    def _mac(self, purpose: bytes, data: str) -> str:
        return b64encode(hmac.new(self._key, purpose + data.encode("ascii"), hashlib.sha256).digest())

    def register(self, client: OAuthClientInformationFull) -> None:
        """Reemplaza el client_id y el client_secret generados por el SDK por
        los firmados (el SDK devuelve este mismo objeto en la respuesta)."""
        metadata = client.model_dump(mode="json", exclude={"client_id", "client_secret"}, exclude_none=True)
        payload = b64encode(zlib.compress(json.dumps(metadata, separators=(",", ":")).encode("utf-8"), 9))
        client.client_id = f"{payload}.{self._mac(b'id', payload)}"
        if client.client_secret is not None:
            client.client_secret = self._mac(b"secret", client.client_id)
        logger.info("OAuth: cliente registrado: %s", client.client_name)

    def get(self, client_id: str) -> OAuthClientInformationFull | None:
        if not client_id.isascii():
            return None
        payload, sep, signature = client_id.partition(".")
        if not sep or not hmac.compare_digest(signature, self._mac(b"id", payload)):
            return None
        try:
            metadata = json.loads(zlib.decompress(b64decode(payload)))
        except (ValueError, zlib.error):
            return None
        client = OAuthClientInformationFull.model_validate({**metadata, "client_id": client_id})
        if client.token_endpoint_auth_method != "none":
            client.client_secret = self._mac(b"secret", client_id)
        return client
