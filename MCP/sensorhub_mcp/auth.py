"""Autenticación del servidor MCP con un token fijo.

El servidor exige `Authorization: Bearer <MCP_AUTH_TOKEN>` en cada pedido. Es un
único secreto compartido, declarado en el .env del MCP: el cliente lo envía como
encabezado fijo (en claude.ai, "Request headers" del conector personalizado).
No hay OAuth, usuarios ni expiración: para rotar el token se cambia el .env y se
recrea el contenedor.
"""

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

from .config import MCP_AUTH_TOKEN


class AuthConfigError(RuntimeError):
    """Falta el token de autenticación."""


def check_auth_config() -> None:
    if not MCP_AUTH_TOKEN:
        raise AuthConfigError("Falta MCP_AUTH_TOKEN en el .env del MCP (generar uno con: openssl rand -hex 32)")


class BearerTokenMiddleware:
    """Middleware ASGI: responde 401 si el pedido HTTP no trae el token correcto."""

    def __init__(self, app: ASGIApp, token: str = MCP_AUTH_TOKEN) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self._authorized(scope):
            body = json.dumps({"error": "unauthorized", "error_description": "Token inválido o ausente"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        for name, value in scope["headers"]:
            if name == b"authorization":
                scheme, _, credentials = value.partition(b" ")
                return scheme.lower() == b"bearer" and hmac.compare_digest(credentials.strip(), self._token)
        return False
