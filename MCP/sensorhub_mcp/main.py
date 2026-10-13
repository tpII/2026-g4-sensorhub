"""Punto de entrada del servidor MCP."""

import logging

from . import resources, tools  # noqa: F401  (registran resources y tools al importarse)
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

    mcp.run(transport="streamable-http", **HTTP_TRANSPORT_OPTIONS)


if __name__ == "__main__":
    main()
