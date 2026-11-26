"""Tools de sensor de presencia y movimiento PIR — ver wiki, 06, sección 3.2.

A diferencia de DHT y Switch, el canal `pir/telemetry` usa `retain=false` (ver
wiki, 03, sección 6), por lo que ninguna tool de PIR lee mensajes retenidos de
MQTT: todas consultan directamente la medición `pir_telemetry` en InfluxDB."""

import logging
from datetime import datetime, timezone
from typing import Optional

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from ..influx_client import (
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
from .status import offline_lines

logger = logging.getLogger(__name__)



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


async def _offline_note(
    ctx: Context, device_id: str, start_dt: datetime, end_dt: datetime, subject: str
) -> str:
    """Aclaración para respuestas sobre un rango: '' si el sensor estuvo online
    todo el tiempo; si no, lista los intervalos offline. `subject` describe qué no
    puede garantizarse (p. ej. 'que no hubo movimiento')."""
    lines = await offline_lines(ctx, device_id, start_dt, end_dt)
    if not lines:
        return ""
    return (
        f" Pero el sensor no estuvo online durante todo el rango, por lo que no puede "
        f"asegurarse {subject}. Intervalos en los que el dispositivo estuvo fuera de línea:\n"
        + "\n".join(lines)
    )


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


@mcp.tool(annotations=read_only("Última detección de movimiento de un sensor PIR"))
async def get_last_motion_event(device_id: DeviceIdParam, ctx: Context) -> str:
    """
    Obtiene la fecha y hora de la última vez que un sensor PIR detectó
    movimiento efectivamente (motion=true), ignorando los eventos posteriores de
    vuelta al reposo (motion=false). Usar para preguntas como '¿cuándo fue la
    última vez que hubo movimiento en la cocina?'. Para consultar si hubo
    movimiento en una ventana de tiempo, usar had_motion_in_range. Si el usuario
    nombró el sensor por un lugar o un apodo, llamar primero a resolve_device_id
    con device_type='pir'; si dio su device_id, usarlo directamente. Si entre esa
    detección y ahora el sensor estuvo fuera de línea, la respuesta lo informa
    junto con los intervalos del corte: informarlos al usuario, porque pudo haber
    movimientos posteriores sin detectar. Si el sensor nunca detectó movimiento,
    la respuesta lo indica.
    """
    device_id = await _pir(device_id)

    now_dt = datetime.now(timezone.utc)
    try:
        last_dt = await run_blocking(
            query_latest_true_event,
            influx(ctx),
            "pir_telemetry",
            "motion",
            device_id,
        )
    except Exception as e:
        logger.error("Error consultando InfluxDB para PIR '%s': %s", device_id, e)
        raise ToolError(INFLUX_UNAVAILABLE) from e

    if last_dt is not None:
        # Cualquier corte del sensor posterior a la última detección significa que pudo
        # haber movimientos que no se registraron. El sensor estaba online en ese
        # instante (acababa de publicar), así que no hace falta mirar el pasado.
        time_str = last_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = f"La última detección de movimiento en el sensor PIR '{device_id}' fue a las {time_str}."
        lines = await offline_lines(ctx, device_id, last_dt, now_dt, online_at_start=True)
        if not lines:
            return msg
        return (
            msg
            + " Pero entre ese instante y ahora el sensor estuvo fuera de línea en los "
            "siguientes intervalos, por lo que pudo haber movimientos posteriores sin detectar:\n"
            + "\n".join(lines)
        )

    return f"El sensor PIR '{device_id}' nunca registró movimiento (en todo el historial disponible)."


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
    usar count_motion_events. Si la respuesta indica que el sensor estuvo offline
    en algún intervalo del rango, informar esos intervalos al usuario y no afirmar
    que no hubo movimiento: solo se puede asegurar en los períodos en que el
    sensor estuvo online. Si el usuario nombró el sensor por un lugar o un
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

    note = await _offline_note(ctx, device_id, start_dt, effective_end, "que no hubo movimiento")

    if prior_active is None and not bool_points:
        return f"No hay registros del sensor PIR '{device_id}' entre {rango}." + note

    return f"No se detectó movimiento en el sensor PIR '{device_id}' entre {rango}." + note


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
    tiempo (por ejemplo '¿cuántas veces entró alguien a la cocina hoy?'). Si la
    respuesta indica que el sensor estuvo offline en algún intervalo del rango,
    informar esos intervalos: el conteo es un mínimo, pudo haber movimientos no
    detectados mientras estuvo desconectado. Si el usuario nombró el sensor por
    un lugar o un apodo, llamar primero a resolve_device_id con
    device_type='pir'; si dio su device_id, usarlo directamente.
    """
    device_id = await _pir(device_id)
    start_dt, effective_end, _ = normalize_past_range(start, end)
    prior_active, bool_points = await _query_pir_series(ctx, device_id, start_dt, effective_end)
    summary = summarize_binary_state_range(prior_active, bool_points, start_dt, effective_end)
    rango = _format_range(start_dt, effective_end)
    note = await _offline_note(
        ctx, device_id, start_dt, effective_end, "que el conteo sea completo (pudo haber movimientos no detectados)"
    )

    if not summary.had_data:
        return f"No hay registros de actividad del sensor PIR '{device_id}' entre {rango}." + note

    if summary.activations == 0:
        return (
            f"Entre {rango}, no se registraron eventos de movimiento (0 detecciones) "
            f"en el sensor PIR '{device_id}'." + note
        )

    act_times = _activation_timestamps(prior_active, bool_points)
    if summary.activations == 1:
        t_str = act_times[0].strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            f"Entre {rango}, se registró 1 evento de movimiento en el sensor PIR '{device_id}' "
            f"(a las {t_str})." + note
        )

    first_str = act_times[0].strftime("%Y-%m-%d %H:%M:%S UTC")
    last_str = act_times[-1].strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        f"Entre {rango}, se registraron {summary.activations} eventos de movimiento en el sensor "
        f"PIR '{device_id}' (primero a las {first_str}, último a las {last_str})." + note
    )
