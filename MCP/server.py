#!/usr/bin/env python3
"""
SensorHub - Servidor MCP Streamable HTTP
Expone la lectura de telemetría de temperatura actual desde InfluxDB.
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


# Registra la funcion como una herramienta invocable por el modelo de lenguaje
@mcp.tool()
def get_current_temperature(device_id: str) -> str:
    """
    Obtiene la temperatura actual y la fecha/hora de la última lectura registrada en InfluxDB
    para un sensor de temperatura (tipo DHT) dado su ID exacto.
    
    Args:
        device_id: Identificador exacto del sensor (ejemplo: 'dht_simulado' o MAC '983dae529858').
    """
    # Consulta en Flux para obtener el valor mas reciente de las ultimas 24 horas
    flux_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -24h)
      |> filter(fn: (r) => r._measurement == "dht_telemetry")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r._field == "temperature")
      |> last()
    '''

    try:
        # Abre la conexion con InfluxDB y ejecuta la consulta
        with get_influx_client() as client:
            query_api = client.query_api()
            tables = query_api.query(flux_query, org=INFLUXDB_ORG)

            # Itera las tablas devueltas para extraer la medicion y la marca de tiempo
            for table in tables:
                for record in table.records:
                    temp_val = record.get_value()
                    record_time = record.get_time().strftime("%Y-%m-%d %H:%M:%S UTC")
                    # Retorna el resultado en lenguaje natural con formato legible para el LLM
                    return f"La temperatura actual del sensor '{device_id}' es {float(temp_val):.1f}°C (registrada a las {record_time})."

            # Mensaje descriptivo si el sensor no registro datos en la ventana de tiempo
            return f"No se encontraron lecturas de temperatura en las últimas 24h para el sensor '{device_id}'."

    except Exception as e:
        # Captura cualquier falla de red o autenticacion con la base de datos
        return f"Error al consultar InfluxDB: {str(e)}"


# Punto de entrada principal
if __name__ == "__main__":
    print("Iniciando Servidor MCP SensorHub en modo Streamable HTTP...")
    print(f"Broker MQTT : {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} (listo para uso)")
    print(f"InfluxDB    : {INFLUXDB_URL} (Org: {INFLUXDB_ORG}, Bucket: {INFLUXDB_BUCKET})")
    print(f"Endpoint    : http://{MCP_HOST}:{MCP_PORT}{mcp.settings.streamable_http_path}")

    mcp.run(transport="streamable-http")
