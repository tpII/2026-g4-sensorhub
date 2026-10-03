#!/usr/bin/env python3
"""
SensorHub - Servidor MCP Streamable HTTP
Infraestructura base (conexiones a InfluxDB/MQTT) sin tools activas todavía.
El catálogo de tools a implementar está propuesto en la wiki, página 06
(Diseño de Tools MCP por Dispositivo) — las versiones anteriores de este
archivo no coincidían con esa propuesta (granularidad, nombres o estrategia
de lectura) y se retiraron hasta reconstruirlas alineadas a ese diseño.
"""

import csv
import difflib
import os
import re
from typing import Optional

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

# Registro de dispositivos (device_type, device_id, nombre amigable) para
# resolve_device_id. Se completa a mano por ahora (ver wiki, 06, sección 2.3)
# — a futuro podría poblarse vía un flujo de aprovisionamiento al registrar
# un dispositivo nuevo.
DEVICE_REGISTRY_PATH = os.getenv(
    "DEVICE_REGISTRY_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "devices.csv"),
)

# Umbral de similitud para el fuzzy match de nombres amigables (0-1). El
# default de difflib (0.6) da falsos positivos entre palabras cortas en
# español que comparten muchas letras (p. ej. "cocina" vs "oficina" da 0.77
# de similitud) — con 0.8 ese caso se rechaza sin perder tolerancia a
# errores de tipeo reales ("livin"/"living" da 0.91). Ajustar si en la
# práctica resulta muy laxo o muy estricto — ver "Qué queda abierto" en la
# wiki, 06, sección 4.
DEVICE_MATCH_CUTOFF = 0.8

# Palabras sin valor para identificar un dispositivo (artículos/preposiciones
# sueltos) — se descartan antes de comparar, así "el de la oficina" compara
# contra "oficina" en vez de perder similitud por las palabras de relleno.
_DEVICE_DESCRIPTION_STOPWORDS = {"el", "la", "los", "las", "de", "del", "un", "una"}

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


# Helper: Lee el registro de dispositivos desde DEVICE_REGISTRY_PATH.
# Nunca se le pasa entero al LLM (ver wiki, 06, sección 2.3) — solo lo usa
# resolve_device_id, server-side, para resolver una descripción puntual.
def _load_device_registry() -> list[dict]:
    try:
        with open(DEVICE_REGISTRY_PATH, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def _normalize_device_description(description: str) -> str:
    words = [
        w for w in re.split(r"\s+", description.strip().lower())
        if w not in _DEVICE_DESCRIPTION_STOPWORDS
    ]
    return " ".join(words) if words else description.strip().lower()


@mcp.tool()
def resolve_device_id(description: str, device_type: Optional[str] = None) -> str:
    """
    Traduce una descripción en lenguaje libre de un dispositivo (por ejemplo
    "cocina", "el de la oficina") al device_id exacto que esperan las demás
    tools. Hay que llamarla ANTES de cualquier tool de lectura o de comando,
    y usar el valor que devuelve como argumento device_id de esa tool.

    Si encuentra una coincidencia, el valor devuelto es el device_id en sí
    (un identificador interno) — no corresponde mostrárselo al usuario tal
    cual, sino usarlo para completar la siguiente llamada. Si no encuentra
    ninguna coincidencia razonable, devuelve una explicación en lenguaje
    natural en vez de adivinar el dispositivo más parecido.

    Args:
        description: Cómo se refirió el usuario al dispositivo (un lugar,
            un apodo, lo que haya dicho) — no necesita coincidir exacto con
            el nombre registrado.
        device_type: Tipo de dispositivo si se puede inferir de la pregunta
            ("dht", "pir", "switch"). Opcional: ayuda a desambiguar cuando
            el mismo nombre está registrado para más de un tipo.
    """
    registry = _load_device_registry()
    if device_type:
        registry = [r for r in registry if r["device_type"] == device_type]

    if not registry:
        return "No hay dispositivos registrados todavía para esa búsqueda."

    # Si el usuario (o el LLM) ya pasó un device_id real, no hace falta
    # adivinar nada.
    for entry in registry:
        if entry["device_id"] == description.strip():
            return entry["device_id"]

    friendly_names = [entry["friendly_name"] for entry in registry]
    matches = difflib.get_close_matches(
        _normalize_device_description(description),
        [name.lower() for name in friendly_names],
        n=1,
        cutoff=DEVICE_MATCH_CUTOFF,
    )

    if not matches:
        return (
            f"No identifico ningún dispositivo que coincida con '{description}'. "
            "¿Podrías confirmar el nombre o el lugar del dispositivo?"
        )

    matched_entry = next(
        entry for entry in registry if entry["friendly_name"].lower() == matches[0]
    )
    return matched_entry["device_id"]


# TODO: reconstruir el resto del catálogo de tools siguiendo la propuesta de
# la wiki, página 06 (Diseño de Tools MCP por Dispositivo) — usando
# resolve_device_id antes de cada tool de lectura/comando, y la estrategia
# MQTT-primero/InfluxDB-respaldo para los dispositivos con retain=true + ts
# (sección 3, y 05 sección 4).


# Punto de entrada principal
if __name__ == "__main__":
    print("Iniciando Servidor MCP SensorHub en modo Streamable HTTP...")
    print(f"Broker MQTT : {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} (listo para uso)")
    print(f"InfluxDB    : {INFLUXDB_URL} (Org: {INFLUXDB_ORG}, Bucket: {INFLUXDB_BUCKET})")
    print(f"Endpoint    : http://{MCP_HOST}:{MCP_PORT}{mcp.settings.streamable_http_path}")

    mcp.run(transport="streamable-http")
