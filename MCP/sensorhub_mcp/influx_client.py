"""Cliente de InfluxDB y helpers de consulta Flux reutilizados por las tools.

Las funciones de consulta reciben el cliente compartido que crea el lifespan
del servidor (mcp_app.py) y son síncronas: las tools las ejecutan en un hilo
aparte para no bloquear el bucle de eventos del servidor."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from influxdb_client import InfluxDBClient
from influxdb_client.rest import ApiException

from .config import INFLUXDB_BUCKET, INFLUXDB_ORG, INFLUXDB_PASSWORD, INFLUXDB_URL, INFLUXDB_USERNAME


def get_influx_client() -> InfluxDBClient:
    """Cliente autenticado con el usuario de solo lectura (INFLUXDB_USERNAME /
    INFLUXDB_PASSWORD): la librería abre una sesión (/api/v2/signin) en la
    primera consulta y reutiliza su cookie."""
    return InfluxDBClient(
        url=INFLUXDB_URL,
        username=INFLUXDB_USERNAME,
        password=INFLUXDB_PASSWORD,
        org=INFLUXDB_ORG,
        timeout=10000,
    )


def _query(client: InfluxDBClient, flux_query: str):
    """Ejecuta una consulta Flux. La sesión de InfluxDB vence tras 60 min sin
    uso y la librería no vuelve a hacer signin sola: ante un 401 se descarta la
    cookie (la siguiente consulta abre una sesión nueva) y se reintenta una vez."""
    try:
        return client.query_api().query(flux_query, org=INFLUXDB_ORG)
    except ApiException as e:
        if e.status != 401:
            raise
        client.api_client.cookie = None
        return client.query_api().query(flux_query, org=INFLUXDB_ORG)


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
    tables = _query(client, flux_query)
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
) -> Optional[datetime]:
    """Obtiene la fecha/hora UTC (datetime) del último registro donde `field` vale `true`
    (por ejemplo `motion == true` en `pir_telemetry`), ignorando los eventos
    posteriores con `false`. Busca en todo el historial del bucket (`range(start: 0)`:
    Flux exige un `range()`, y 0 es el inicio de los tiempos) y retorna `None` si
    nunca hubo ninguno."""
    flux_query = f'''
    from(bucket: "{INFLUXDB_BUCKET}")
      |> range(start: 0)
      |> filter(fn: (r) => r._measurement == "{measurement}")
      |> filter(fn: (r) => r.device_id == "{device_id}")
      |> filter(fn: (r) => r._field == "{field}" and r._value == true)
      |> last()
    '''
    tables = _query(client, flux_query)
    for table in tables:
        for record in table.records:
            return record.get_time().astimezone(timezone.utc)
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
    tables = _query(client, flux_query)
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
    tables = _query(client, flux_query)
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
    lookback_days: Optional[int] = 30,
    fetch_prior: bool = True,
) -> tuple[Any, list[tuple[datetime, Any]]]:
    """Trae una serie de estados booleanos en un rango, junto con el estado vigente
    al inicio de ese rango. Sirve para cualquier serie temporal orientada a eventos
    (un actuador encendido/apagado, un sensor que detecta/no detecta, un dispositivo
    online/offline, etc.). Devuelve `(prior_val, points)`:

    - `prior_val`: el último punto anterior a `start_dt`, buscando hasta `lookback_days`
      hacia atrás (o en todo el historial si es `None`).
    - `points`: los puntos `(timestamp_utc, valor)` dentro de `[start_dt, stop_dt)`,
      ordenados cronológicamente.

    En estas series solo se escribe un punto cuando algo cambia. Por eso mirar
    únicamente los puntos dentro del rango lleva a dos errores:

    1. Perder el estado que ya traía el rango. Si el estado cambió antes de `start_dt`
       y no hubo ningún cambio después, no hay puntos dentro del rango, y parecería
       que no hay información. Con el estado previo se sabe en qué estado estuvo todo
       el rango (por ejemplo, 0 s activo en vez del tiempo completo, o un dispositivo
       caído antes del rango dado por conectado).
    2. Contar una transición falsa al inicio. Con QoS 1 el broker puede entregar un
       mensaje duplicado; si el estado previo ya era el mismo, un valor repetido justo
       al comienzo del rango se descarta en vez de contarse como un cambio nuevo.

    Con `fetch_prior=False` se omite la consulta del estado previo (`prior_val` es
    `None`): para cuando el llamador ya conoce el estado al inicio del rango."""
    # `lookback_days=None`: sin límite (Flux exige un inicio de rango; 0 = inicio de los tiempos).
    prior_start = "0" if lookback_days is None else _flux_rfc3339(start_dt - timedelta(days=lookback_days))
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
    if fetch_prior:
        for table in _query(client, prior_query):
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
    for table in _query(client, range_query):
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


def availability_gaps(
    prior_online: Optional[bool],
    points: list[tuple[datetime, bool]],
    start_dt: datetime,
    end_dt: datetime,
) -> list[tuple[datetime, datetime, Optional[bool]]]:
    """Intervalos de `[start_dt, end_dt]` en los que el dispositivo NO estuvo
    confirmado online, a partir de la serie de `device_status.online`.

    Devuelve tuplas `(inicio, fin, estado)` con `estado=False` (offline: llegó un
    `online=false`, típicamente el Last Will) o `estado=None` (sin registro de
    presencia: no hay ningún punto previo que diga en qué estado estaba; el
    llamador decide cómo informarlo).
    Lista vacía = online durante todo el rango."""
    gaps: list[tuple[datetime, datetime, Optional[bool]]] = []
    state = prior_online
    cursor = start_dt
    for raw_ts, online in points:
        ts = min(max(raw_ts, start_dt), end_dt)
        if online is state:
            continue
        if state is not True and ts > cursor:
            gaps.append((cursor, ts, state))
        cursor, state = ts, online
    if state is not True and end_dt > cursor:
        gaps.append((cursor, end_dt, state))
    return gaps
