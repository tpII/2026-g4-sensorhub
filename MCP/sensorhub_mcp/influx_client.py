"""Cliente de InfluxDB y helpers de consulta Flux reutilizados por las tools.

Las funciones de consulta reciben el cliente compartido que crea el lifespan
del servidor (mcp_app.py) y son síncronas: las tools las ejecutan en un hilo
aparte para no bloquear el bucle de eventos del servidor."""

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
