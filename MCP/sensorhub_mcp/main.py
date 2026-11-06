"""Punto de entrada del servidor MCP."""

import logging

import uvicorn

from . import resources, tools  # noqa: F401  (registran resources y tools al importarse)
from .auth import BearerTokenMiddleware, check_auth_config
from .config import (
    INFLUXDB_BUCKET,
    INFLUXDB_ORG,
    INFLUXDB_URL,
    MCP_HOST,
    MCP_HTTP_PATH,
    MCP_PORT,
    MCP_STATELESS_HTTP,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
)
from .mcp_app import HTTP_TRANSPORT_OPTIONS, mcp

logger = logging.getLogger("sensorhub_mcp")


def main() -> None:
    # Los registros del servidor van a stderr (los muestra `docker logs`): la
    # especificación 2026-07-28 declara obsoleto el logging por el protocolo
    # (SEP-2577) y recomienda stderr u OpenTelemetry.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Iniciando servidor MCP SensorHub (Streamable HTTP, %s)", "stateless" if MCP_STATELESS_HTTP else "con sesión")
    logger.info("Broker MQTT: %s:%s", MQTT_BROKER_HOST, MQTT_BROKER_PORT)
    logger.info("InfluxDB: %s (org %s, bucket %s)", INFLUXDB_URL, INFLUXDB_ORG, INFLUXDB_BUCKET)
    logger.info("Endpoint: http://%s:%s%s", MCP_HOST, MCP_PORT, MCP_HTTP_PATH)
    logger.info("Autenticación: token fijo (Authorization: Bearer)")

    check_auth_config()
    # Se arma la app ASGI a mano (en vez de mcp.run) para envolverla con el
    # middleware que exige el token.
    options = {k: v for k, v in HTTP_TRANSPORT_OPTIONS.items() if k != "port"}
    app = mcp.streamable_http_app(**options)
    app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, log_level=mcp.settings.log_level.lower())


if __name__ == "__main__":
    main()
