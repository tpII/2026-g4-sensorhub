"""Tools del canal transversal `status` (presencia / LWT) — ver wiki, 06, sección 3.4.

Son dos, separadas por la forma de la respuesta (wiki, 06, sección 1.2) y por la
fuente de la que leen, siguiendo el criterio de la sección 4 de la página 05:

- `is_device_online`: el estado de ahora. `status` tiene `retain=true` (wiki, 03,
  sección 6), así que el broker entrega el último mensaje conocido en el acto y no
  hace falta tocar InfluxDB.
- `get_device_availability`: la disponibilidad a lo largo de un rango pasado. Eso
  no lo puede responder un único valor retenido: reutiliza `availability_gaps`
  sobre la serie `device_status.online` de InfluxDB.

`offline_lines` vive acá y no en `tools/pir.py` porque no tiene nada de específico
del PIR: las tools de PIR la usan para avisar en qué intervalos no puede
asegurarse una respuesta, y la tool de rango la usa como respuesta en sí misma.

A diferencia del resto del catálogo estas tools no son específicas de un tipo de
dispositivo: `status` es transversal a los tres (wiki, 03, sección 1)."""

import logging
from datetime import datetime, timezone
from typing import Optional

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from ..devices import find_registered_entry
from ..influx_client import availability_gaps, query_state_series
from ..mcp_app import mcp
from ..mqtt_client import fetch_mqtt_retained
from .common import (
    INFLUX_UNAVAILABLE,
    DeviceIdParam,
    RangeEndParam,
    RangeStartParam,
    influx,
    normalize_past_range,
    read_only,
    run_blocking,
    validate_device_id,
)

logger = logging.getLogger(__name__)

TIME_FMT = "%Y-%m-%d %H:%M:%S"

# Cantidad máxima de intervalos offline que se listan en una respuesta.
MAX_LISTED_GAPS = 10


async def offline_lines(
    ctx: Context,
    device_id: str,
    start_dt: datetime,
    end_dt: datetime,
    online_at_start: bool = False,
) -> list[str]:
    """Verifica la disponibilidad (`device_status.online`) del dispositivo durante
    todo `[start_dt, end_dt]`. Devuelve [] si estuvo online todo el tiempo; si no,
    una línea por intervalo offline (acotada a MAX_LISTED_GAPS).

    Por defecto el estado al inicio se busca en el historial (último `online`
    anterior a `start_dt`). Con `online_at_start=True` se da por sabido que el
    dispositivo estaba online en `start_dt` (p. ej. porque acababa de publicar una
    detección) y no se consulta el pasado."""
    try:
        prior_val, raw_points = await run_blocking(
            query_state_series,
            influx(ctx),
            "device_status",
            "online",
            device_id,
            start_dt,
            end_dt,
            # `online=true` se publica una sola vez al conectar (sin latido periódico): el estado
            # vigente al inicio puede venir de un mensaje muy antiguo, así que se busca sin límite.
            lookback_days=None,
            fetch_prior=not online_at_start,
        )
    except Exception as e:
        logger.error("Error consultando presencia de '%s': %s", device_id, e)
        raise ToolError(INFLUX_UNAVAILABLE) from e

    prior_online = True if online_at_start else (prior_val if isinstance(prior_val, bool) else None)
    points = [(ts, v) for ts, v in raw_points if isinstance(v, bool)]
    gaps = availability_gaps(prior_online, points, start_dt, end_dt)

    # state=None (sin ningún registro de presencia) se informa igual como offline:
    # no hay evidencia de que el dispositivo estuviera conectado.
    lines = [
        f"- {g_start.strftime(TIME_FMT)} a {g_end.strftime(TIME_FMT)} UTC (offline)"
        for g_start, g_end, _ in gaps[:MAX_LISTED_GAPS]
    ]
    if len(gaps) > MAX_LISTED_GAPS:
        lines.append(f"- ... y {len(gaps) - MAX_LISTED_GAPS} intervalo(s) más")
    return lines


@mcp.tool(annotations=read_only("Conexión actual de un dispositivo"))
async def is_device_online(device_id: DeviceIdParam) -> str:
    """
    Indica si un dispositivo está conectado al broker en este momento. Vale para
    cualquier tipo de dispositivo (dht, pir o switch). Para saber si estuvo
    conectado durante un período pasado, usar get_device_availability. Si el
    usuario nombró el dispositivo por un lugar o un apodo, llamar primero a
    resolve_device_id.
    """
    device_id = await validate_device_id(device_id)
    entry = await run_blocking(find_registered_entry, device_id)
    topic = f"sensorhub/{entry['device_type']}/{device_id}/status"

    retained = await run_blocking(fetch_mqtt_retained, topic)
    if retained is None or "online" not in retained:
        return (
            f"No hay ningún mensaje de presencia retenido para el dispositivo '{device_id}', "
            "así que no puede confirmarse si está conectado."
        )

    if not retained["online"]:
        # El Last Will no lleva `ts` (wiki, 03, sección 2): se fija al conectar y el
        # broker lo publica recién al detectar la caída, así que no hay hora de origen.
        return f"El dispositivo '{device_id}' no está conectado."

    ts = retained.get("ts")
    if ts is None:
        return f"El dispositivo '{device_id}' está conectado."
    desde = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime(TIME_FMT)
    return f"El dispositivo '{device_id}' está conectado desde las {desde} UTC."


@mcp.tool(annotations=read_only("Disponibilidad de un dispositivo en un rango"))
async def get_device_availability(
    device_id: DeviceIdParam, start: RangeStartParam, end: RangeEndParam, ctx: Context
) -> str:
    """
    Indica si un dispositivo estuvo conectado al broker durante todo un período
    pasado y, si no, en qué intervalos estuvo fuera de línea. Vale para cualquier
    tipo de dispositivo (dht, pir o switch). Para el estado de ahora, usar
    is_device_online. Si el usuario nombró el dispositivo por un lugar o un apodo,
    llamar primero a resolve_device_id.
    """
    device_id = await validate_device_id(device_id)
    start_dt, end_dt, clamped = normalize_past_range(start, end)

    lines = await offline_lines(ctx, device_id, start_dt, end_dt)
    rango = f"{start_dt.strftime(TIME_FMT)} y {end_dt.strftime(TIME_FMT)} UTC"
    aviso = " El fin del rango se recortó al instante actual." if clamped else ""

    if not lines:
        return f"El dispositivo '{device_id}' estuvo conectado entre {rango}.{aviso}"
    return (
        f"El dispositivo '{device_id}' no estuvo conectado durante todo el período entre "
        f"{rango}.{aviso} Intervalos fuera de línea:\n" + "\n".join(lines)
    )
