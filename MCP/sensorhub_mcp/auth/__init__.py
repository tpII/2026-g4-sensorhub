"""Autenticación OAuth 2.1 del servidor MCP, delegada en Keycloak.

Keycloak es el servidor de autorización: registra a los clientes (claude.ai,
ChatGPT, Claude Code, etc.), muestra el login y emite los tokens. El servidor
MCP es solo el servidor de recursos: publica sus Protected Resource Metadata
(RFC 9728), que apuntan al realm de Keycloak, y verifica el token de cada
pedido (verifier.py). La configuración del realm está en MCP/keycloak/.

Uso desde mcp_app.py:

    verifier = build_token_verifier()                   # None si está desactivada
    mcp = MCPServer(..., **oauth_server_options(verifier))
"""

import logging
from typing import Any

from mcp.server.auth.settings import AuthSettings

from ..config import MCP_AUTH_ENABLED, MCP_AUTH_ISSUER, MCP_AUTH_JWKS_URL, MCP_HTTP_PATH, MCP_PUBLIC_URL
from .verifier import KeycloakTokenVerifier

__all__ = ["build_token_verifier", "oauth_server_options"]

logger = logging.getLogger(__name__)


class AuthConfigError(RuntimeError):
    """Configuración de autenticación incompleta."""


def build_token_verifier() -> KeycloakTokenVerifier | None:
    if not MCP_AUTH_ENABLED:
        logger.warning("Autenticación DESACTIVADA (MCP_AUTH_ENABLED=false): cualquiera que llegue al servidor puede usarlo")
        return None
    if not MCP_PUBLIC_URL.startswith(("https://", "http://")):
        raise AuthConfigError("Falta MCP_PUBLIC_URL (p. ej. https://mcp.ejemplo.com)")
    if not MCP_AUTH_ISSUER.startswith(("https://", "http://")):
        raise AuthConfigError("Falta MCP_AUTH_ISSUER, el realm de Keycloak (p. ej. https://auth.ejemplo.com/realms/sensorhub)")
    return KeycloakTokenVerifier(
        issuer=MCP_AUTH_ISSUER,
        jwks_url=MCP_AUTH_JWKS_URL or f"{MCP_AUTH_ISSUER}/protocol/openid-connect/certs",
        resource_url=MCP_PUBLIC_URL + MCP_HTTP_PATH,
    )


def oauth_server_options(verifier: KeycloakTokenVerifier | None) -> dict[str, Any]:
    """Argumentos de MCPServer para activar OAuth (vacío si está desactivada)."""
    if verifier is None:
        return {}
    return {
        "token_verifier": verifier,
        "auth": AuthSettings(
            issuer_url=verifier.issuer,
            resource_server_url=verifier.resource_url,
            # Solo se aceptan tokens emitidos para este endpoint MCP (RFC 8707)
            validate_token_resource=True,
        ),
    }
