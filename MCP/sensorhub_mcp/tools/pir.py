"""Tools de sensor de presencia y movimiento PIR — ver wiki, 06, sección 3.2.

A diferencia de DHT y Switch, el canal `pir/telemetry` usa `retain=false` (ver
wiki, 03, sección 6), por lo que ninguna tool de PIR lee mensajes retenidos de
MQTT: todas consultan directamente la medición `pir_telemetry` en InfluxDB."""

import logging
from datetime import datetime
from typing import Optional

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from ..influx_client import (
    query_latest_telemetry,
    query_latest_true_event,
    query_state_series,
    summarize_binary_state_range,
)
from ..mcp_app import mcp
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

# Un sensor PIR es puramente orientado a eventos: en un ambiente sin tránsito
# puede pasar días sin emitir un mensaje sin que eso implique una falla.
PIR_STATE_LOOKBACK_HOURS = 24 * 7
PIR_LAST_EVENT_LOOKBACK_HOURS = 24 * 30


async def _pir(device_id: str) -> str:
    return await validate_device_id(device_id, "pir", "sensor PIR")


def _format_range(start_dt: datetime, end_dt: datetime) -> str:
    return (
        f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} y "
        f"{end_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )


async def _query_pir_series(
    ctx: Context, device_id: str, start_dt: datetime, end_dt: datetime
) -> tuple[Optional[bool], list[tuple[datetime, bool]]]:
    try:
        prior_val, raw_points = await run_blocking(
            query_state_series,
            influx(ctx),
            "pir_telemetry",
            "motion",
            device_id,
            start_dt,
            end_dt,
        )
    except Exception as e:
        logger.error("Error consultando InfluxDB para PIR '%s': %s", device_id, e)
        raise ToolError(INFLUX_UNAVAILABLE) from e

    prior_active = prior_val if isinstance(prior_val, bool) else None
    bool_points = [(ts, val) for ts, val in raw_points if isinstance(val, bool)]
    return prior_active, bool_points


def _activation_timestamps(
    prior_active: Optional[bool], points: list[tuple[datetime, bool]]
) -> list[datetime]:
    """Instantes exactos de cada transición hacia `motion=True` (`False -> True`
    o primer registro `None -> True`), coherente con `summarize_binary_state_range`."""
    current = prior_active
    times: list[datetime] = []
    for ts, is_motion in points:
        if is_motion:
            if current is not True:
                times.append(ts)
                current = True
        else:
            current = False
    return times


@mcp.tool(annotations=read_only("Estado actual de movimiento de un sensor PIR"))
async def get_last_motion_state(device_id: DeviceIdParam, ctx: Context) -> str:
    """
    Obtiene el último estado reportado por un sensor PIR (si hay movimiento
    activo en este momento o si la zona está en reposo) junto con la hora de
    ese registro. Usar para preguntas sobre el presente ('¿hay alguien en la
    cocina ahora?', '¿hay movimiento?'). Para saber cuándo fue la última vez
    que se detectó movimiento aunque ahora esté en reposo, usar
    get_last_motion_event. Si el usuario nombró el sensor por un lugar o un
    apodo, llamar primero a resolve_device_id con device_type='pir'; si dio su
    device_id, usarlo directamente.
    """
    device_id = await _pir(device_id)

    try:
        motion_val, time_str = await run_blocking(
            query_latest_telemetry,
            influx(ctx),
            "pir_telemetry",
            "motion",
            device_id,
            PIR_STATE_LOOKBACK_HOURS,
        )
    except Exception as e:
        logger.error("Error consultando InfluxDB para PIR '%s': %s", device_id, e)
        raise ToolError(INFLUX_UNAVAILABLE) from e

    if motion_val is True:
        return (
            f"El sensor PIR '{device_id}' reporta movimiento activo "
            f"(último estado: movimiento detectado a las {time_str})."
        )
    if motion_val is False:
        return (
            f"El sensor PIR '{device_id}' no reporta movimiento actualmente "
            f"(último estado: reposo desde las {time_str})."
        )
    return f"No se encontraron registros en los últimos 7 días para el sensor PIR '{device_id}'."


@mcp.tool(annotations=read_only("Última detección de movimiento de un sensor PIR"))
async def get_last_motion_event(device_id: DeviceIdParam, ctx: Context) -> str:
    """
    Obtiene la fecha y hora de la última vez que un sensor PIR detectó
    movimiento efectivamente (motion=true), ignorando los eventos posteriores de
    vuelta al reposo (motion=false). Usar para preguntas como '¿cuándo fue la
    última vez que hubo movimiento en la cocina?'. Para consultar si hay
    movimiento activo ahora mismo, usar get_last_motion_state. Si el usuario
    nombró el sensor por un lugar o un apodo, llamar primero a resolve_device_id
    con device_type='pir'; si dio su device_id, usarlo directamente.
    """
    device_id = await _pir(device_id)

    try:
        time_str = await run_blocking(
            query_latest_true_event,
            influx(ctx),
            "pir_telemetry",
            "motion",
            device_id,
            PIR_LAST_EVENT_LOOKBACK_HOURS,
        )
    except Exception as e:
        logger.error("Error consultando InfluxDB para PIR '%s': %s", device_id, e)
        raise ToolError(INFLUX_UNAVAILABLE) from e

    if time_str is None:
        return (
            f"No se registraron detecciones de movimiento en los últimos 30 días "
            f"para el sensor PIR '{device_id}'."
        )
    return f"La última detección de movimiento en el sensor PIR '{device_id}' fue a las {time_str}."


@mcp.tool(annotations=read_only("Verificar si hubo movimiento en un rango"))
async def had_motion_in_range(
    device_id: DeviceIdParam,
    start: RangeStartParam,
    end: RangeEndParam,
    ctx: Context,
) -> str:
    """
    Verifica si un sensor PIR detectó movimiento al menos una vez dentro de un
    rango de tiempo (por ejemplo '¿hubo movimiento en la cocina en la última
    hora?'). Si se necesita saber cuántas veces exactas se detectó movimiento,
    usar count_motion_events. Si el usuario nombró el sensor por un lugar o un
    apodo, llamar primero a resolve_device_id con device_type='pir'; si dio su
    device_id, usarlo directamente.
    """
    device_id = await _pir(device_id)
    start_dt, effective_end, _ = normalize_past_range(start, end)
    prior_active, bool_points = await _query_pir_series(ctx, device_id, start_dt, effective_end)
    rango = _format_range(start_dt, effective_end)

    true_times = [ts for ts, is_motion in bool_points if is_motion]
    if true_times:
        if len(true_times) == 1:
            t_str = true_times[0].strftime("%Y-%m-%d %H:%M:%S UTC")
            return f"Sí, se detectó movimiento en el sensor PIR '{device_id}' entre {rango} (a las {t_str})."
        first_str = true_times[0].strftime("%Y-%m-%d %H:%M:%S UTC")
        last_str = true_times[-1].strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"Sí, se detectó movimiento en el sensor PIR '{device_id}' entre {rango} "
            f"(primera detección a las {first_str}, última a las {last_str})."
        )

    # Pulso de movimiento que comenzó justo antes de `start_dt` y cesó dentro del rango
    if prior_active is True and bool_points and bool_points[0][1] is False:
        end_motion_str = bool_points[0][0].strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"Sí, había movimiento activo en el sensor PIR '{device_id}' al inicio del período "
            f"(iniciado antes de {start_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC y finalizado a las {end_motion_str})."
        )

    if prior_active is None and not bool_points:
        return f"No hay registros del sensor PIR '{device_id}' entre {rango}."

    return f"No se detectó movimiento en el sensor PIR '{device_id}' entre {rango}."


@mcp.tool(annotations=read_only("Contar eventos de movimiento en un rango"))
async def count_motion_events(
    device_id: DeviceIdParam,
    start: RangeStartParam,
    end: RangeEndParam,
    ctx: Context,
) -> str:
    """
    Cuenta cuántas veces se activó la detección de movimiento (transiciones de
    reposo a movimiento, false -> true) en un sensor PIR durante un rango de
    tiempo (por ejemplo '¿cuántas veces entró alguien a la cocina hoy?'). Si el
    usuario nombró el sensor por un lugar o un apodo, llamar primero a
    resolve_device_id con device_type='pir'; si dio su device_id, usarlo
    directamente.
    """
    device_id = await _pir(device_id)
    start_dt, effective_end, _ = normalize_past_range(start, end)
    prior_active, bool_points = await _query_pir_series(ctx, device_id, start_dt, effective_end)
    summary = summarize_binary_state_range(prior_active, bool_points, start_dt, effective_end)
    rango = _format_range(start_dt, effective_end)

    if not summary.had_data:
        return f"No hay registros de actividad del sensor PIR '{device_id}' entre {rango}."

    if summary.activations == 0:
        return (
            f"Entre {rango}, no se registraron eventos de movimiento (0 detecciones) "
            f"en el sensor PIR '{device_id}'."
        )

    act_times = _activation_timestamps(prior_active, bool_points)
    if summary.activations == 1:
        t_str = act_times[0].strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"Entre {rango}, se registró 1 evento de movimiento en el sensor PIR '{device_id}' "
            f"(a las {t_str})."
        )

    first_str = act_times[0].strftime("%Y-%m-%d %H:%M:%S UTC")
    last_str = act_times[-1].strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        f"Entre {rango}, se registraron {summary.activations} eventos de movimiento en el sensor "
        f"PIR '{device_id}' (primero a las {first_str}, último a las {last_str})."
    )

