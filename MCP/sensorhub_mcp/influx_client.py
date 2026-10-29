"""Cliente de InfluxDB y helpers de consulta Flux reutilizados por las tools.

Las funciones de consulta reciben el cliente compartido que crea el lifespan
del servidor (mcp_app.py) y son síncronas: las tools las ejecutan en un hilo
aparte para no bloquear el bucle de eventos del servidor."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from influxdb_client import InfluxDBClient

from .config import INFLUXDB_BUCKET, INFLUXDB_ORG, INFLUXDB_TOKEN, INFLUXDB_URL


def get_influx_client() -> InfluxDBClient:
    return InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG,
        timeout=10000,
    )


def query_latest_telemetry(client: InfluxDBClient, measurement: str, field: str, device_id: str, hours: int = 24):
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
    tables = client.query_api().query(flux_query, org=INFLUXDB_ORG)
    for table in tables:
        for record in table.records:
            val = record.get_value()
            time_str = record.get_time().strftime("%Y-%m-%d %H:%M:%S UTC")
            return val, time_str
    return None, None


def query_latest_true_event(
    client: InfluxDBClient,
    measurement: str,
    field: str,
    device_id: str,
    hours: int = 24 * 30,
) -> Optional[str]:
    """Obtiene la fecha/hora UTC del último registro donde `field` vale `true`
    (por ejemplo `motion == true` en `pir_telemetry`), ignorando los eventos
    posteriores con `false`. Retorna `None` si no hubo ninguno en `hours`."""
    flux_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -{hours}h)
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r._field == "{field}" and r._value == true)
      |> last()
    '''
    tables = client.query_api().query(flux_query, org=INFLUXDB_ORG)
    for table in tables:
        for record in table.records:
            return record.get_time().astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return None


# Última temperatura+humedad en una sola consulta (mismo punto/payload — ver
# wiki, 06, sección 3.1, por qué conviene una sola query en vez de dos).
def query_latest_climate(client: InfluxDBClient, device_id: str, hours: int = 24):
    flux_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: -{hours}h)
      |> filter(fn: (r) => r._measurement == "dht_telemetry")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"], desc: true)
      |> limit(n: 1)
    '''
    tables = client.query_api().query(flux_query, org=INFLUXDB_ORG)
    for table in tables:
        for record in table.records:
            time_str = record.get_time().strftime("%Y-%m-%d %H:%M:%S UTC")
            return record.values.get("temperature"), record.values.get("humidity"), time_str
    return None, None, None


# Aplica una función de agregación de Flux (max/min/mean/last) sobre un
# field entre dos instantes ya formateados como RFC3339.
def query_field_aggregate(
    client: InfluxDBClient, measurement: str, field: str, device_id: str, agg: str, start_rfc3339: str, stop_rfc3339: str
):
    flux_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start_rfc3339}, stop: {stop_rfc3339})
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r._field == "{field}")
      |> {agg}()
    '''
    tables = client.query_api().query(flux_query, org=INFLUXDB_ORG)
    for table in tables:
        for record in table.records:
            # mean() no trae columna _time (no hay un instante único al
            # que atribuirle el promedio); max()/min()/last() sí la conservan.
            t = record.values.get("_time")
            time_str = t.strftime("%Y-%m-%d %H:%M:%S UTC") if t is not None else None
            return record.get_value(), time_str
    return None, None


def _flux_rfc3339(moment: datetime) -> str:
    """Formatea un datetime en UTC como literal RFC 3339 para Flux, conservando
    subsegundos si los tiene (InfluxDB almacena con precisión de milisegundos)."""
    utc_dt = moment.astimezone(timezone.utc) if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    return utc_dt.isoformat().replace("+00:00", "Z")


@dataclass
class StateRangeSummary:
    """Resumen de transiciones y permanencia en estado activo sobre [start, end],
    reutilizable entre dispositivos discretos (switch on/off, pir motion true/false;
    ver wiki 06 secciones 3.3 y 4)."""

    had_data: bool
    prior_active: Optional[bool]
    currently_active: Optional[bool]
    activations: int
    deactivations: int
    active_seconds: float


def query_state_series(
    client: InfluxDBClient,
    measurement: str,
    field: str,
    device_id: str,
    start_dt: datetime,
    stop_dt: datetime,
    lookback_days: int = 30,
) -> tuple[Any, list[tuple[datetime, Any]]]:
    """Obtiene el estado vigente al inicio del rango (último punto anterior a
    `start_dt`, mirando hasta `lookback_days` hacia atrás) y la serie ordenada
    cronológicamente de puntos `(timestamp_utc, valor)` dentro de `[start_dt, stop_dt)`.

    Consultar el estado previo evita dos errores clásicos en series orientadas a
    eventos: reportar 0 s encendidos cuando el actuador se prendió antes de `start_dt`
    y siguió prendido todo el rango sin emitir mensajes nuevos, o contar un
    duplicado QoS 1 al comienzo del rango como si fuera una transición nueva."""
    prior_start = _flux_rfc3339(start_dt - timedelta(days=lookback_days))
    start_rfc3339 = _flux_rfc3339(start_dt)
    # En Flux, `stop` es exclusivo; +1 ms incluye lecturas tomadas exactamente en `stop_dt`.
    stop_rfc3339 = _flux_rfc3339(stop_dt + timedelta(milliseconds=1))

    prior_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {prior_start}, stop: {start_rfc3339})
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r._field == "{field}")
      |> last()
    '''
    prior_val = None
    for table in client.query_api().query(prior_query, org=INFLUXDB_ORG):
        for record in table.records:
            prior_val = record.get_value()

    range_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: {start_rfc3339}, stop: {stop_rfc3339})
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r._field == "{field}")
      |> sort(columns: ["_time"], desc: false)
    '''
    points: list[tuple[datetime, Any]] = []
    for table in client.query_api().query(range_query, org=INFLUXDB_ORG):
        for record in table.records:
            points.append((record.get_time().astimezone(timezone.utc), record.get_value()))

    return prior_val, points


def summarize_binary_state_range(
    prior_active: Optional[bool],
    points: list[tuple[datetime, bool]],
    start_dt: datetime,
    end_dt: datetime,
) -> StateRangeSummary:
    """Recorre una secuencia cronológica de estados booleanos sobre `[start_dt, end_dt]`
    contando transiciones reales (ignora repeticiones del mismo estado por reenvíos
    idempotentes o QoS 1) y acumulando el tiempo total en estado activo."""
    if prior_active is None and not points:
        return StateRangeSummary(
            had_data=False,
            prior_active=None,
            currently_active=None,
            activations=0,
            deactivations=0,
            active_seconds=0.0,
        )

    current: Optional[bool] = prior_active
    active_since: Optional[datetime] = start_dt if prior_active is True else None
    activations = 0
    deactivations = 0
    active_seconds = 0.0

    for raw_ts, is_active in points:
        ts = min(max(raw_ts, start_dt), end_dt)
        if is_active:
            if current is not True:
                activations += 1
                current = True
                active_since = ts
        else:
            if current is True:
                deactivations += 1
                if active_since is not None:
                    active_seconds += max(0.0, (ts - active_since).total_seconds())
                current = False
                active_since = None
            elif current is None:
                current = False

    if current is True and active_since is not None:
        active_seconds += max(0.0, (end_dt - active_since).total_seconds())

    return StateRangeSummary(
        had_data=True,
        prior_active=prior_active,
        currently_active=current,
        activations=activations,
        deactivations=deactivations,
        active_seconds=active_seconds,
    )
