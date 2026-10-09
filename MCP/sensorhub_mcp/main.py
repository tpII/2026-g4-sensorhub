"""Punto de entrada del servidor MCP."""

import logging

from . import resources, tools  # noqa: F401  (registran resources y tools al importarse)
from .config import (
    INFLUXDB_BUCKET,
    INFLUXDB_ORG,
    INFLUXDB_URL,
    MCP_HOST,
    MCP_PORT,
    MCP_STATELESS_HTTP,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
)
from .mcp_app import mcp

logger = logging.getLogger("sensorhub_mcp")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Iniciando servidor MCP SensorHub (Streamable HTTP, %s)", "stateless" if MCP_STATELESS_HTTP else "con sesión")
    logger.info("Broker MQTT: %s:%s", MQTT_BROKER_HOST, MQTT_BROKER_PORT)
    logger.info("InfluxDB: %s (org %s, bucket %s)", INFLUXDB_URL, INFLUXDB_ORG, INFLUXDB_BUCKET)
    logger.info("Endpoint: http://%s:%s%s", MCP_HOST, MCP_PORT, mcp.settings.streamable_http_path)

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
