"""Autenticación OAuth 2.1 de un solo usuario para el servidor MCP.

El propio servidor hace de servidor de autorización: los clientes (claude.ai,
ChatGPT, Claude Code, etc.) se registran solos, mandan al usuario a una
pantalla de login con una única contraseña (MCP_AUTH_PASSWORD) y obtienen
tokens con los que llaman al endpoint MCP. No guarda nada: los tokens y los
clientes registrados van firmados, así que arranca en frío solo con el .env y
un reinicio no corta ninguna sesión.

Uso desde mcp_app.py:

    provider = build_oauth_provider()                    # None si está desactivada
    mcp = MCPServer(..., **oauth_server_options(provider))
    if provider:
        register_login_routes(mcp, provider)
"""

import logging
from typing import Any

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions

from ..config import (
    MCP_AUTH_ENABLED,
    MCP_AUTH_PASSWORD,
    MCP_AUTH_SECRET,
    MCP_HTTP_PATH,
    MCP_PUBLIC_URL,
)
from .login import register_login_routes
from .provider import SingleUserOAuthProvider

__all__ = ["build_oauth_provider", "oauth_server_options", "register_login_routes"]

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 12
MIN_SECRET_LENGTH = 32


class AuthConfigError(RuntimeError):
    """Configuración de autenticación incompleta o insegura."""


def build_oauth_provider() -> SingleUserOAuthProvider | None:
    if not MCP_AUTH_ENABLED:
        logger.warning("Autenticación DESACTIVADA (MCP_AUTH_ENABLED=false): cualquiera que llegue al servidor puede usarlo")
        return None
    if not MCP_PUBLIC_URL:
        raise AuthConfigError("Falta MCP_PUBLIC_URL (p. ej. https://mcp.ejemplo.com)")
    if len(MCP_AUTH_PASSWORD) < MIN_PASSWORD_LENGTH:
        raise AuthConfigError(f"MCP_AUTH_PASSWORD tiene que tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    if len(MCP_AUTH_SECRET) < MIN_SECRET_LENGTH:
        raise AuthConfigError(f"MCP_AUTH_SECRET tiene que tener al menos {MIN_SECRET_LENGTH} caracteres (openssl rand -hex 32)")
    if MCP_AUTH_SECRET == MCP_AUTH_PASSWORD:
        raise AuthConfigError("MCP_AUTH_SECRET y MCP_AUTH_PASSWORD tienen que ser distintos")
    return SingleUserOAuthProvider(
        issuer_url=MCP_PUBLIC_URL,
        resource_url=MCP_PUBLIC_URL + MCP_HTTP_PATH,
        password=MCP_AUTH_PASSWORD,
        secret=MCP_AUTH_SECRET,
    )


def oauth_server_options(provider: SingleUserOAuthProvider | None) -> dict[str, Any]:
    """Argumentos de MCPServer para activar OAuth (vacío si está desactivada)."""
    if provider is None:
        return {}
    return {
        "auth_server_provider": provider,
        "auth": AuthSettings(
            issuer_url=provider.issuer_url,
            resource_server_url=provider.resource_url,
            # Registro dinámico abierto (lo usan claude.ai y ChatGPT) y sin scopes:
            # hay un único usuario con acceso a todo
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=False),
            # Solo se aceptan tokens emitidos para este endpoint MCP (RFC 8707)
            validate_token_resource=True,
        ),
    }
