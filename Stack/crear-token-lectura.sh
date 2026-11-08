#!/bin/sh
# Crea en InfluxDB un token de SOLO LECTURA sobre el bucket del proyecto y lo imprime.
# El servidor MCP solo consulta datos, por lo que no necesita el token de administrador
# (con el que escribe EMQX): se pega el valor impreso en INFLUXDB_TOKEN de MCP/.env y se
# recrea el contenedor del MCP (cd ../MCP && docker compose up -d mcp-server).
# Requiere el stack levantado (contenedor sensorhub_influxdb).
set -e
docker exec sensorhub_influxdb sh -c '
BID=$(influx bucket list --org "$DOCKER_INFLUXDB_INIT_ORG" --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" \
        --name "$DOCKER_INFLUXDB_INIT_BUCKET" --hide-headers | cut -f1)
influx auth create --org "$DOCKER_INFLUXDB_INIT_ORG" --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" \
        --read-bucket "$BID" --description "mcp-solo-lectura" --json | sed -n "s/.*\"token\": \"\([^\"]*\)\".*/\1/p"
'
