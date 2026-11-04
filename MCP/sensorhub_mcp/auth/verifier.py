"""Verificación de los access tokens que emite Keycloak.

Keycloak firma los tokens como JWT (RS256) con claves que publica en su JWKS.
El servidor MCP no guarda nada: por cada pedido verifica la firma con esas
claves (cacheadas), que el emisor sea el realm configurado, que el token no
haya vencido y que su audiencia sea este endpoint MCP (RFC 8707). Un token
emitido para otro servicio del mismo realm no pasa."""

import logging

import anyio.to_thread
import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)

# Algoritmo de firma por defecto de Keycloak. Fijarlo evita aceptar tokens
# firmados con otro algoritmo (p. ej. "none" o HS256 con la clave pública)
ALGORITHMS = ["RS256"]
# Las claves de firma se vuelven a pedir cada este tiempo, o antes si llega un
# token firmado con una clave desconocida (rotación de claves en Keycloak)
JWKS_CACHE_SECONDS = 60 * 60


class KeycloakTokenVerifier(TokenVerifier):
    def __init__(self, *, issuer: str, jwks_url: str, resource_url: str):
        self.issuer = issuer
        self.resource_url = resource_url
        self._jwks = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=JWKS_CACHE_SECONDS, timeout=5)

    def _decode(self, token: str) -> dict:
        signing_key = self._jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            issuer=self.issuer,
            audience=self.resource_url,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            # PyJWKClient es síncrono (pide el JWKS por HTTP): va en un hilo aparte
            claims = await anyio.to_thread.run_sync(self._decode, token)
        except jwt.PyJWKClientConnectionError as exc:
            logger.error("OAuth: no se pudo obtener el JWKS de Keycloak: %s", exc)
            return None
        except jwt.PyJWTError as exc:
            logger.info("OAuth: token rechazado: %s", exc)
            return None
        # Keycloak marca los access tokens con typ "Bearer" (los ID tokens llevan "ID")
        if claims.get("typ", "Bearer") != "Bearer":
            return None
        return AccessToken(
            token=token,
            client_id=claims.get("azp", ""),
            scopes=claims.get("scope", "").split(),
            expires_at=claims["exp"],
            resource=self.resource_url,
            subject=claims["sub"],
            claims={"iss": claims["iss"], "preferred_username": claims.get("preferred_username")},
        )
