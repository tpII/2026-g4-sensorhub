"""Punto de entrada del servidor MCP."""

from . import tools  # noqa: F401  (registra las tools al importar el paquete)
from .config import INFLUXDB_BUCKET, INFLUXDB_ORG, INFLUXDB_URL, MCP_HOST, MCP_PORT, MQTT_BROKER_HOST, MQTT_BROKER_PORT
from .mcp_app import mcp


def main() -> None:
    print("Iniciando Servidor MCP SensorHub en modo Streamable HTTP...")
    print(f"Broker MQTT : {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} (listo para uso)")
    print(f"InfluxDB    : {INFLUXDB_URL} (Org: {INFLUXDB_ORG}, Bucket: {INFLUXDB_BUCKET})")
    print(f"Endpoint    : http://{MCP_HOST}:{MCP_PORT}{mcp.settings.streamable_http_path}")

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
