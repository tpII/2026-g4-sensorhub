"""Instancia compartida del servidor MCP (clase MCPServer del SDK oficial, v2):
los módulos de tools y resources importan `mcp` de acá para registrarse con
@mcp.tool() / @mcp.resource()."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from influxdb_client import InfluxDBClient
from mcp.server.mcpserver import MCPServer
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
async def lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
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

mcp = MCPServer(name="SensorHub", instructions=INSTRUCTIONS, lifespan=lifespan)

# Opciones del transporte Streamable HTTP. En el SDK v2 no son parte del
# constructor: se pasan a mcp.run() (ver main.py).
# - transport_security: la especificación exige validar Host y Origin para evitar
#   ataques de DNS rebinding. El SDK lo activa por su cuenta solo al escuchar en
#   localhost; como el contenedor escucha en 0.0.0.0, se activa explícitamente.
# - stateless_http: sin sesión por cliente (escala horizontal). La revisión
#   2026-07-28 de la especificación ya es sin estado; esta opción solo afecta a
#   los clientes de revisiones anteriores (handshake con initialize).
HTTP_TRANSPORT_OPTIONS = {
    "host": MCP_HOST,
    "port": MCP_PORT,
    "streamable_http_path": MCP_HTTP_PATH,
    "stateless_http": MCP_STATELESS_HTTP,
    "transport_security": TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=MCP_ALLOWED_HOSTS,
        allowed_origins=MCP_ALLOWED_ORIGINS,
    ),
}
