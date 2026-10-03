#!/usr/bin/env python3
"""
SensorHub - Servidor MCP Streamable HTTP
Infraestructura base (conexiones a InfluxDB/MQTT) sin tools activas todavía.
El catálogo de tools a implementar está propuesto en la wiki, página 06
(Diseño de Tools MCP por Dispositivo) — las versiones anteriores de este
archivo no coincidían con esa propuesta (granularidad, nombres o estrategia
de lectura) y se retiraron hasta reconstruirlas alineadas a ese diseño.
"""

import os
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient

# Carga de variables de entorno
load_dotenv()

# Configuracion de conexion al broker MQTT para uso futuro
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "sensorhub_emqx")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))

# Configuracion de conexion a InfluxDB
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://sensorhub_influxdb:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "sensorhub_admin_secret_token_123")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "sensorhub")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sensorhub")

# Configuracion del servidor MCP
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_HTTP_PATH = os.getenv("MCP_HTTP_PATH", "/mcp")

# Inicializacion de FastMCP en la ruta /mcp
mcp = FastMCP("SensorHub", host=MCP_HOST, port=MCP_PORT)
mcp.settings.streamable_http_path = MCP_HTTP_PATH


# Helper: Cliente InfluxDB
def get_influx_client() -> InfluxDBClient:
    return InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG,
        timeout=10000
    )


# Helper: Cliente MQTT (preparado para actuadores y comandos en etapas futuras)
def get_mqtt_client(client_id: str = "mcp_client") -> mqtt.Client:
    client = mqtt.Client(client_id=client_id)
    return client


# Helper: Consulta genérica a InfluxDB
def _query_latest_telemetry(measurement: str, field: str, device_id: str, hours: int = 24):
    """
    Ejecuta una consulta Flux a InfluxDB obteniendo el último valor de un campo específico
    para un measurement y device_id dados. Retorna una tupla (valor, timestamp) o (None, None).
    """
    flux_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -{hours}h)
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r._field == "{field}")
      |> last()
    '''
    with get_influx_client() as client:
        query_api = client.query_api()
        tables = query_api.query(flux_query, org=INFLUXDB_ORG)
        for table in tables:
            for record in table.records:
                val = record.get_value()
                time_str = record.get_time().strftime("%Y-%m-%d %H:%M:%S UTC")
                return val, time_str
    return None, None


# TODO: reconstruir el catálogo de tools siguiendo la propuesta de la wiki,
# página 06 (Diseño de Tools MCP por Dispositivo) — incluyendo la resolución
# de device_id por nombre amigable (sección 2) antes de las tools de lectura,
# y la estrategia MQTT-primero/InfluxDB-respaldo para los dispositivos con
# retain=true + ts (sección 3, y 05 sección 4).


# Punto de entrada principal
if __name__ == "__main__":
    print("Iniciando Servidor MCP SensorHub en modo Streamable HTTP...")
    print(f"Broker MQTT : {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} (listo para uso)")
    print(f"InfluxDB    : {INFLUXDB_URL} (Org: {INFLUXDB_ORG}, Bucket: {INFLUXDB_BUCKET})")
    print(f"Endpoint    : http://{MCP_HOST}:{MCP_PORT}{mcp.settings.streamable_http_path}")

    mcp.run(transport="streamable-http")
