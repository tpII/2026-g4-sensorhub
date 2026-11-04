"""Variables de entorno y configuración de conexión del servidor MCP."""

import os

from dotenv import load_dotenv

load_dotenv()

# Conexion al broker MQTT
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "sensorhub_emqx")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
# Usuario MQTT del MCP (MQTT_MCP_USERNAME / MQTT_MCP_PASSWORD de Stack/.env)
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "mcp")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

# Conexion a InfluxDB
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://sensorhub_influxdb:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "sensorhub_admin_secret_token_123")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "sensorhub")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sensorhub")

# Transporte y red del servidor MCP
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_HTTP_PATH = os.getenv("MCP_HTTP_PATH", "/mcp")

# Modo stateless de Streamable HTTP para clientes de revisiones del protocolo
# anteriores a 2026-07-28 (las que usan el handshake initialize): cada petición
# se atiende sin sesión, lo que permite escalar horizontalmente. Desactivado por
# defecto porque, sin sesión, esos clientes no pueden recibir elicitation (ver
# resolve_device_id). La revisión 2026-07-28 ya es sin estado y no se ve afectada.
MCP_STATELESS_HTTP = os.getenv("MCP_STATELESS_HTTP", "false").strip().lower() in ("1", "true", "yes")


def _csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


# Protección contra DNS rebinding (validación de los encabezados Host y Origin),
# exigida por la especificación de Streamable HTTP. Se admite el comodín de
# puerto "host:*". Para exponer el servidor con un túnel (ngrok, etc.), agregar
# su dominio a ambas listas.
MCP_ALLOWED_HOSTS = _csv_list(os.getenv("MCP_ALLOWED_HOSTS", "localhost:*,127.0.0.1:*,sensorhub_mcp:*"))
MCP_ALLOWED_ORIGINS = _csv_list(os.getenv("MCP_ALLOWED_ORIGINS", "http://localhost:*,http://127.0.0.1:*"))

# Autenticación OAuth 2.1 con Keycloak como servidor de autorización (paquete
# auth/). Activada por defecto: con "false" el servidor queda abierto, solo
# para desarrollo local.
MCP_AUTH_ENABLED = os.getenv("MCP_AUTH_ENABLED", "true").strip().lower() in ("1", "true", "yes")
# URL pública del servidor, sin path (p. ej. https://mcp.ejemplo.com): junto con
# MCP_HTTP_PATH es el recurso protegido, la audiencia que tienen que traer los tokens.
MCP_PUBLIC_URL = os.getenv("MCP_PUBLIC_URL", "").strip().rstrip("/")
# Realm de Keycloak que emite los tokens, tal como figura en su claim "iss"
# (p. ej. https://auth.ejemplo.com/realms/sensorhub).
MCP_AUTH_ISSUER = os.getenv("MCP_AUTH_ISSUER", "").strip().rstrip("/")
# De dónde bajar las claves públicas de Keycloak. Por defecto, el JWKS del
# issuer; en Docker conviene la URL interna (http://sensorhub_keycloak:8080/...),
# que no depende del dominio público.
MCP_AUTH_JWKS_URL = os.getenv("MCP_AUTH_JWKS_URL", "").strip()
