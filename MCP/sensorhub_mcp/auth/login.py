"""Pantalla de login (/oauth/login): el paso del flujo OAuth en el que el
usuario se identifica. Muestra qué cliente pide acceso y a qué sitio va a
volver, para que se pueda reconocer un pedido que no inició uno mismo."""

import asyncio
import html
import logging

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .provider import SingleUserOAuthProvider

logger = logging.getLogger(__name__)

LOGIN_PATH = "/oauth/login"

# Demora tras una contraseña incorrecta. Los intentos se atienden de a uno
# (_attempt_lock), así que limita la fuerza bruta a ~1 intento por segundo.
FAILED_LOGIN_DELAY_SECONDS = 1.0

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}

_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SensorHub · Acceso</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #f4f5f7; color: #1d2330; margin: 0;
         display: flex; min-height: 100vh; align-items: center; justify-content: center; padding: 16px; }}
  main {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,.08);
          padding: 28px; width: 100%; max-width: 380px; box-sizing: border-box; }}
  h1 {{ font-size: 1.25rem; margin: 0 0 12px; }}
  p {{ line-height: 1.45; margin: 0 0 12px; }}
  .error {{ color: #b42318; }}
  input {{ width: 100%; padding: 10px; font-size: 1rem; border: 1px solid #c4c8d0;
           border-radius: 8px; box-sizing: border-box; margin: 4px 0 16px; }}
  button {{ width: 100%; padding: 10px; font-size: 1rem; border: 0; border-radius: 8px;
            background: #1f6feb; color: #fff; cursor: pointer; }}
</style>
</head>
<body><main>{body}</main></body>
</html>"""


def _page(body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(body=body), status_code=status_code, headers=_SECURITY_HEADERS)


def _expired_page() -> HTMLResponse:
    return _page(
        "<h1>Pedido vencido</h1>"
        "<p>Este pedido de acceso ya no es válido. Volvé a conectar SensorHub desde el cliente.</p>",
        status_code=400,
    )


def _login_form(request_id: str, client_name: str, redirect_host: str, error: str | None = None) -> HTMLResponse:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return _page(
        "<h1>Acceso a SensorHub</h1>"
        f"<p><strong>{html.escape(client_name)}</strong> pide acceso a los sensores y actuadores. "
        f"Al autorizar, vas a volver a <strong>{html.escape(redirect_host)}</strong>.</p>"
        f"{error_html}"
        f'<form method="post" action="{LOGIN_PATH}">'
        f'<input type="hidden" name="request" value="{html.escape(request_id)}">'
        '<label for="password">Contraseña</label>'
        '<input id="password" name="password" type="password" autocomplete="current-password" required autofocus>'
        "<button type=\"submit\">Autorizar</button>"
        "</form>",
        status_code=401 if error else 200,
    )


def register_login_routes(mcp: MCPServer, provider: SingleUserOAuthProvider) -> None:
    attempt_lock = asyncio.Lock()

    @mcp.custom_route(LOGIN_PATH, methods=["GET", "POST"], include_in_schema=False)
    async def login(request: Request) -> Response:
        if request.method == "GET":
            request_id = request.query_params.get("request", "")
            pending = provider.get_pending_login(request_id)
            if pending is None:
                return _expired_page()
            return _login_form(request_id, pending.client_name, pending.redirect_host)

        form = await request.form()
        request_id = str(form.get("request", ""))
        password = str(form.get("password", ""))
        pending = provider.get_pending_login(request_id)
        if pending is None:
            return _expired_page()

        async with attempt_lock:
            if not provider.check_password(password):
                logger.warning("OAuth: contraseña incorrecta en el login de %s", pending.client_name)
                await asyncio.sleep(FAILED_LOGIN_DELAY_SECONDS)
                if not provider.register_failed_attempt(request_id):
                    return _expired_page()
                return _login_form(request_id, pending.client_name, pending.redirect_host, "Contraseña incorrecta.")

        redirect_url = provider.complete_login(request_id)
        if redirect_url is None:
            return _expired_page()
        logger.info("OAuth: acceso autorizado para %s", pending.client_name)
        return RedirectResponse(redirect_url, status_code=302, headers={"Cache-Control": "no-store"})
