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


# Registra la funcion como una herramienta invocable por el modelo de lenguaje
@mcp.tool()
def get_current_temperature(device_id: str) -> str:
    """
    Obtiene la temperatura actual y la fecha/hora de la última lectura registrada en InfluxDB
    para un sensor de temperatura (tipo DHT) dado su ID exacto.
    
    Args:
        device_id: Identificador exacto del sensor (ejemplo: 'dht_simulado' o MAC '983dae529858').
    """
    try:
        val, time_str = _query_latest_telemetry("dht_telemetry", "temperature", device_id)
        if val is not None:
            return f"La temperatura actual del sensor '{device_id}' es {float(val):.1f}°C (registrada a las {time_str})."
        return f"No se encontraron lecturas de temperatura en las últimas 24h para el sensor '{device_id}'."
    except Exception as e:
        return f"Error al consultar InfluxDB: {str(e)}"


@mcp.tool()
def get_current_humidity(device_id: str) -> str:
    """
    Obtiene la humedad relativa actual y la fecha/hora de la última lectura registrada en InfluxDB
    para un sensor de clima (tipo DHT) dado su ID exacto.

    Args:
        device_id: Identificador exacto del sensor (ejemplo: 'dht_simulado' o MAC '983dae529858').
    """
    try:
        val, time_str = _query_latest_telemetry("dht_telemetry", "humidity", device_id)
        if val is not None:
            return f"La humedad actual del sensor '{device_id}' es {float(val):.1f}% (registrada a las {time_str})."
        return f"No se encontraron lecturas de humedad en las últimas 24h para el sensor '{device_id}'."
    except Exception as e:
        return f"Error al consultar InfluxDB: {str(e)}"


@mcp.tool()
def get_motion_state(device_id: str) -> str:
    """
    Obtiene el último estado de movimiento registrado en InfluxDB para un sensor PIR dado su ID exacto.
    El campo 'motion' es booleano: true indica detección activa, false indica zona despejada.

    Args:
        device_id: Identificador exacto del sensor PIR (ejemplo: MAC '983dae529858').
    """
    try:
        val, time_str = _query_latest_telemetry("pir_telemetry", "motion", device_id)
        if val is not None:
            estado = "movimiento detectado 🔴" if val else "zona despejada ✅"
            return f"El sensor PIR '{device_id}' reporta {estado} (última lectura: {time_str})."
        return f"No se encontraron eventos de movimiento en las últimas 24h para el sensor '{device_id}'."
    except Exception as e:
        return f"Error al consultar InfluxDB: {str(e)}"


@mcp.tool()
def get_switch_state(device_id: str) -> str:
    """
    Obtiene el último estado confirmado del actuador Switch registrado en InfluxDB para un dispositivo
    dado su ID exacto. El campo 'state' es un string: 'on' (encendido) o 'off' (apagado).

    Args:
        device_id: Identificador exacto del actuador switch (ejemplo: MAC '9454c5b096b0').
    """
    try:
        val, time_str = _query_latest_telemetry("switch_telemetry", "state", device_id)
        if val is not None:
            estado = "encendido 💡" if val == "on" else "apagado ⬛"
            return f"El actuador switch '{device_id}' está {estado} (último acuse: {time_str})."
        return f"No se encontraron registros de estado en las últimas 24h para el switch '{device_id}'."
    except Exception as e:
        return f"Error al consultar InfluxDB: {str(e)}"


@mcp.tool()
def list_devices(hours: int = 24) -> str:
    """
    Lista todos los dispositivos (device_id y device_type) que publicaron telemetría en InfluxDB
    durante las últimas N horas. Útil para descubrir qué sensores y actuadores están activos
    en la red SensorHub sin necesidad de conocer los IDs de antemano.

    Args:
        hours: Ventana de tiempo hacia atrás en horas (por defecto: 24).
               Valores recomendados: 1 (última hora), 24 (último día), 168 (última semana).
    """
    # Consulta los tres measurements que registran telemetría de dispositivos
    measurements = [
        ("dht_telemetry", "dht"),
        ("pir_telemetry", "pir"),
        ("switch_telemetry", "switch"),
    ]

    found = []

    try:
        with get_influx_client() as client:
            query_api = client.query_api()

            for measurement, device_type in measurements:
                flux_query = f'''
                from(bucket: "{INFLUXDB_BUCKET}")
                  |> range(start: -{hours}h)
                  |> filter(fn: (r) => r._measurement == "{measurement}")
                  |> keep(columns: ["device_id"])
                  |> distinct(column: "device_id")
                '''
                tables = query_api.query(flux_query, org=INFLUXDB_ORG)

                for table in tables:
                    for record in table.records:
                        dev_id = record.get_value()
                        found.append(f"  - [{device_type}] {dev_id}")

        if not found:
            return f"No se encontraron dispositivos con actividad en las últimas {hours}h."

        device_list = "\n".join(found)
        return (
            f"Dispositivos activos en SensorHub (últimas {hours}h): {len(found)} encontrados.\n"
            f"{device_list}"
        )

    except Exception as e:
        return f"Error al consultar InfluxDB: {str(e)}"


# Punto de entrada principal
if __name__ == "__main__":
    print("Iniciando Servidor MCP SensorHub en modo Streamable HTTP...")
    print(f"Broker MQTT : {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} (listo para uso)")
    print(f"InfluxDB    : {INFLUXDB_URL} (Org: {INFLUXDB_ORG}, Bucket: {INFLUXDB_BUCKET})")
    print(f"Endpoint    : http://{MCP_HOST}:{MCP_PORT}{mcp.settings.streamable_http_path}")

    mcp.run(transport="streamable-http")
