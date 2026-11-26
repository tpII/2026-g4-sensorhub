#!/bin/sh
# ==============================================================================
# SensorHub - Usuario de solo lectura para el servidor MCP
#
# La imagen oficial de InfluxDB corre los scripts de /docker-entrypoint-initdb.d
# una sola vez, en el arranque en frío (volumen de datos vacío), después de
# crear la org, el bucket y el usuario admin (DOCKER_INFLUXDB_INIT_*).
#
# Crea INFLUXDB_READER_USERNAME como *miembro* (no owner) de la org: InfluxDB
# le da permiso de lectura sobre los recursos de la org y le niega escribir,
# borrar, crear buckets o tokens, o ver los tokens existentes. El MCP se
# autentica con este usuario y contraseña en lugar del token de admin.
#
# Para aplicarlo sobre un volumen ya inicializado (sin borrar datos):
#   docker exec sensorhub_influxdb /docker-entrypoint-initdb.d/01-usuario-lectura.sh
# ==============================================================================
set -e

: "${INFLUXDB_READER_USERNAME:?Falta INFLUXDB_READER_USERNAME}"
: "${INFLUXDB_READER_PASSWORD:?Falta INFLUXDB_READER_PASSWORD}"

ORG="${DOCKER_INFLUXDB_INIT_ORG:?Falta DOCKER_INFLUXDB_INIT_ORG}"
TOKEN="${DOCKER_INFLUXDB_INIT_ADMIN_TOKEN:?Falta DOCKER_INFLUXDB_INIT_ADMIN_TOKEN}"

if influx user list -t "$TOKEN" -n "$INFLUXDB_READER_USERNAME" >/dev/null 2>&1; then
    echo ">> [SensorHub Bootstrap] El usuario $INFLUXDB_READER_USERNAME ya existe, no se modifica."
    exit 0
fi

echo ">> [SensorHub Bootstrap] Creando usuario de solo lectura $INFLUXDB_READER_USERNAME en la org $ORG..."
# --org lo agrega como miembro de la org (no como owner)
influx user create -t "$TOKEN" \
    -n "$INFLUXDB_READER_USERNAME" \
    -p "$INFLUXDB_READER_PASSWORD" \
    -o "$ORG" >/dev/null
echo ">> [SensorHub Bootstrap] Usuario $INFLUXDB_READER_USERNAME creado."
