"""Servidor de autorización OAuth 2.1 de un solo usuario.

Implementa la interfaz OAuthAuthorizationServerProvider del SDK: el SDK monta
los endpoints estándar (/authorize, /token, /register y los metadatos en
/.well-known/) y valida los pedidos (PKCE, redirect_uri, autenticación del
cliente); este proveedor decide qué se emite y qué se acepta.

Flujo: /authorize guarda el pedido y redirige a la pantalla de login
(login.py); con la contraseña correcta se emite un código de autorización de
un solo uso, que el cliente canjea en /token por un access token (1 h) y un
refresh token (30 días)."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from .clients import ClientRegistry
from .tokens import TokenSigner

ACCESS_TOKEN_TTL_SECONDS = 60 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
AUTHORIZATION_CODE_TTL_SECONDS = 5 * 60
# Tiempo para completar el login desde que el cliente abre /authorize
LOGIN_REQUEST_TTL_SECONDS = 10 * 60
# Intentos de contraseña por pedido de login; después hay que volver a empezar
MAX_LOGIN_ATTEMPTS = 5

# Hay un único usuario: todos los tokens se emiten a su nombre
SUBJECT = "sensorhub-admin"


@dataclass
class PendingLogin:
    """Pedido de /authorize esperando que el usuario ingrese la contraseña."""

    client: OAuthClientInformationFull
    params: AuthorizationParams
    expires_at: float
    attempts: int = 0

    @property
    def client_name(self) -> str:
        return self.client.client_name or self.client.client_id

    @property
    def redirect_host(self) -> str:
        return urlparse(str(self.params.redirect_uri)).netloc


class SingleUserOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, *, issuer_url: str, resource_url: str, password: str, secret: str):
        self.issuer_url = issuer_url
        self.resource_url = resource_url
        self._password_digest = hashlib.sha256(password.encode("utf-8")).digest()
        self._signer = TokenSigner(secret, password)
        self._clients = ClientRegistry(secret)
        # Lo único en memoria: pedidos de login y códigos de autorización, que viven
        # minutos (un reinicio en medio de un login solo obliga a reintentarlo)
        self._pending: dict[str, PendingLogin] = {}
        self._codes: dict[str, AuthorizationCode] = {}

    # --- Clientes (Dynamic Client Registration) ---

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients.register(client_info)

    # --- Autorización y login ---

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        # El único recurso que protege este servidor es su endpoint MCP (RFC 8707)
        if params.resource and params.resource.rstrip("/") != self.resource_url:
            raise AuthorizeError(error="invalid_target", error_description=f"Recurso desconocido: {params.resource}")
        self._purge_expired()
        request_id = secrets.token_urlsafe(32)
        self._pending[request_id] = PendingLogin(client, params, time.time() + LOGIN_REQUEST_TTL_SECONDS)
        return f"{self.issuer_url}/oauth/login?request={request_id}"

    def get_pending_login(self, request_id: str) -> PendingLogin | None:
        pending = self._pending.get(request_id)
        if pending is None or pending.expires_at < time.time():
            return None
        return pending

    def check_password(self, password: str) -> bool:
        # Se comparan los hashes para que el tiempo no dependa del largo de la contraseña
        return hmac.compare_digest(hashlib.sha256(password.encode("utf-8")).digest(), self._password_digest)

    def register_failed_attempt(self, request_id: str) -> bool:
        """Cuenta un intento fallido; devuelve False si el pedido se agotó."""
        pending = self._pending.get(request_id)
        if pending is None:
            return False
        pending.attempts += 1
        if pending.attempts >= MAX_LOGIN_ATTEMPTS:
            del self._pending[request_id]
            return False
        return True

    def complete_login(self, request_id: str) -> str | None:
        """Tras un login correcto, emite el código de autorización y devuelve la
        URL de vuelta al cliente (su redirect_uri con el código y el state)."""
        pending = self._pending.pop(request_id, None)
        if pending is None or pending.expires_at < time.time():
            return None
        params = pending.params
        code = secrets.token_urlsafe(32)
        self._codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + AUTHORIZATION_CODE_TTL_SECONDS,
            client_id=pending.client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self.resource_url,
            subject=SUBJECT,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    def _purge_expired(self) -> None:
        now = time.time()
        self._pending = {k: v for k, v in self._pending.items() if v.expires_at >= now}
        self._codes = {k: v for k, v in self._codes.items() if v.expires_at >= now}

    # --- Canje de códigos y tokens ---

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Un solo uso: se descarta antes de emitir los tokens
        self._codes.pop(authorization_code.code, None)
        return self._issue_tokens(client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        claims = self._signer.verify(refresh_token, "refresh")
        if claims is None or claims.get("cid") != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=claims.get("scp", []),
            expires_at=claims["exp"],
            resource=self.resource_url,
            subject=SUBJECT,
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        return self._issue_tokens(client.client_id, scopes or refresh_token.scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        claims = self._signer.verify(token, "access")
        if claims is None:
            return None
        return AccessToken(
            token=token,
            client_id=claims.get("cid", ""),
            scopes=claims.get("scp", []),
            expires_at=claims["exp"],
            resource=self.resource_url,
            subject=SUBJECT,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # Los tokens no se guardan, así que no se pueden revocar de a uno: el
        # endpoint /revoke está deshabilitado. Para cortar todas las sesiones,
        # cambiar MCP_AUTH_PASSWORD o MCP_AUTH_SECRET.
        return None

    def _issue_tokens(self, client_id: str, scopes: list[str]) -> OAuthToken:
        access_token, _ = self._signer.issue("access", ACCESS_TOKEN_TTL_SECONDS, cid=client_id, scp=scopes)
        refresh_token, _ = self._signer.issue("refresh", REFRESH_TOKEN_TTL_SECONDS, cid=client_id, scp=scopes)
        return OAuthToken(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(scopes) if scopes else None,
            refresh_token=refresh_token,
        )
