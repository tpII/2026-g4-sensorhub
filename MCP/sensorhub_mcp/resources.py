"""Resources del servidor: datos de contexto de solo lectura que el cliente
puede adjuntar a la conversación sin que el modelo tenga que invocar una tool
(ver wiki, 06, sección 2.2). Importar este módulo los registra."""

import json

from .mcp_app import mcp

# Catálogo fijo de tipos de dispositivo del contrato de mensajería (wiki, 03).
# Permite que el modelo asocie "¿hay alguien en la cocina?" con un sensor pir
# sin que el usuario mencione el tipo. Los device_id concretos NO se exponen
# acá: crecen con cada dispositivo y se resuelven con resolve_device_id.
DEVICE_TYPES = [
    {
        "device_type": "dht",
        "descripcion": "Sensor de temperatura y humedad ambiente.",
        "mide": ["temperature (°C)", "humidity (%)"],
        "tools": ["get_current_climate", "get_climate_at", "get_climate_trend"],
    },
    {
        "device_type": "pir",
        "descripcion": "Sensor de movimiento o presencia (infrarrojo pasivo).",
        "mide": ["motion (true/false)"],
        "tools": [],
    },
    {
        "device_type": "switch",
        "descripcion": "Actuador de relé, por ejemplo una luz, con confirmación física del estado.",
        "mide": ["state (on/off)"],
        "tools": [],
    },
]


@mcp.resource(
    "sensorhub://device-types",
    name="device_types",
    title="Tipos de dispositivo",
    description="Tipos de dispositivo de SensorHub: qué mide cada uno y qué tools lo consultan.",
    mime_type="application/json",
)
def device_types() -> str:
    return json.dumps(DEVICE_TYPES, ensure_ascii=False, indent=2)
