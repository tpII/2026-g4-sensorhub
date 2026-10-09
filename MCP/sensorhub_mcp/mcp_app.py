"""Instancia compartida de FastMCP — los módulos de tools y resources importan
`mcp` de acá para registrarse con @mcp.tool() / @mcp.resource()."""

import logging
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from influxdb_client import InfluxDBClient
from mcp.server.fastmcp import FastMCP
from mcp import types
from mcp.server.transport_security import TransportSecuritySettings

from .config import (
    MCP_ALLOWED_HOSTS,
    MCP_ALLOWED_ORIGINS,
    MCP_HOST,
    MCP_HTTP_PATH,
    MCP_PORT,
    MCP_STATELESS_HTTP,
)
from .influx_client import get_influx_client

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Recursos compartidos durante toda la vida del servidor. Las tools los
    obtienen con ctx.request_context.lifespan_context."""

    influx: InfluxDBClient


# Lifespan: hook de arranque y cierre del servidor. El cliente de InfluxDB se
# crea una sola vez (mantiene su pool de conexiones HTTP) en lugar de uno por
# consulta, y se cierra al apagar el servidor. El cliente MQTT, en cambio, se
# crea por llamada a propósito (ver mqtt_client.fetch_mqtt_retained).
@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    influx = get_influx_client()
    logger.info("Cliente de InfluxDB inicializado")
    try:
        yield AppContext(influx=influx)
    finally:
        influx.close()
        logger.info("Cliente de InfluxDB cerrado")


# Instrucciones del servidor: el cliente las entrega al modelo al conectarse,
# como contexto general que vale para todas las tools.
INSTRUCTIONS = (
    "SensorHub expone sensores y actuadores físicos de un hogar o laboratorio. "
    "Cada dispositivo tiene un device_id (su dirección MAC: 12 caracteres hexadecimales) "
    "y puede tener un nombre amigable registrado (un lugar o un apodo, como 'living'). "
    "Si el usuario nombra un dispositivo por un lugar o un apodo, obtener primero su "
    "device_id con resolve_device_id; si da el device_id, usarlo directamente. "
    "El resource sensorhub://device-types describe los tipos de dispositivo disponibles."
)

mcp = FastMCP(
    "SensorHub",
    instructions=INSTRUCTIONS,
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_HTTP_PATH,
    stateless_http=MCP_STATELESS_HTTP,
    lifespan=lifespan,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=MCP_ALLOWED_HOSTS,
        allowed_origins=MCP_ALLOWED_ORIGINS,
    ),
)


# Logging por el protocolo MCP (notifications/message). La especificación pide
# que un servidor que emite logs declare la capacidad "logging" y atienda
# logging/setLevel; FastMCP no lo hace por sí solo, así que se registra el
# handler en el servidor de bajo nivel. El nivel se guarda por sesión: cada
# cliente elige cuánto detalle quiere recibir (por defecto, "info").
LOG_LEVELS = ["debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"]
DEFAULT_LOG_LEVEL = "info"
_session_log_levels: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


@mcp._mcp_server.set_logging_level()
async def _set_logging_level(level: types.LoggingLevel) -> None:
    _session_log_levels[mcp._mcp_server.request_context.session] = level


def session_log_level(session) -> str:
    return _session_log_levels.get(session, DEFAULT_LOG_LEVEL)
