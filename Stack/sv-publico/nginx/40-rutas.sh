#!/bin/sh
set -eu

# ==============================================================================
# SensorHub - Genera la tabla dominio → máquina de nginx (/etc/nginx/rutas.map)
# a partir de rutas.conf. Cada máquina se resuelve por MagicDNS como
# <máquina>.<TS_TAILNET>. Lo corre el entrypoint oficial de nginx antes de
# arrancar; si hay un error, el contenedor no levanta.
# ==============================================================================

: "${TS_TAILNET:?Falta TS_TAILNET en .env}"
RUTAS_FILE="/etc/sensorhub/rutas.conf"
SALIDA="/etc/nginx/rutas.map"

if [ ! -f "$RUTAS_FILE" ]; then
    echo ">> [SensorHub Rutas] Falta rutas.conf (copiar rutas.conf.example y completarlo)" >&2
    exit 1
fi

awk -v tailnet="$TS_TAILNET" '
    function error(msg) { print ">> [SensorHub Rutas] rutas.conf: " msg > "/dev/stderr"; fallo = 1 }
    /^[ \t]*(#|$)/           { next }
    NF != 2                  { error("línea mal formada: " $0); next }
    $2 !~ /^[a-z0-9-]+$/     { error("nombre de máquina inválido para " $1 ": " $2); next }
    visto[tolower($1)]++     { error("dominio repetido: " $1); next }
    {
        printf "    %s %s.%s:443;\n", tolower($1), $2, tailnet
        print ">> [SensorHub Rutas] " $1 " -> " $2 "." tailnet > "/dev/stderr"
    }
    END { exit fallo }
' "$RUTAS_FILE" > "$SALIDA"
