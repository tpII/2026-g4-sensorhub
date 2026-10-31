#!/bin/sh
set -eu

# ==============================================================================
# SensorHub - Genera la tabla dominio → máquina de nginx (/etc/nginx/rutas.map)
# a partir de rutas.conf y peers.conf. Lo corre el entrypoint oficial de nginx
# antes de arrancar; si hay un error, el contenedor no levanta.
# ==============================================================================

PEERS_FILE="/etc/sensorhub/peers.conf"
RUTAS_FILE="/etc/sensorhub/rutas.conf"
SALIDA="/etc/nginx/rutas.map"

for f in "$PEERS_FILE" "$RUTAS_FILE"; do
    if [ ! -f "$f" ]; then
        echo ">> [SensorHub Rutas] Falta $(basename "$f") (copiar el .example y completarlo)" >&2
        exit 1
    fi
done

awk -v peers="$PEERS_FILE" '
    function error(msg) { print ">> [SensorHub Rutas] rutas.conf: " msg > "/dev/stderr"; fallo = 1 }
    BEGIN {
        while ((getline linea < peers) > 0) {
            if (linea ~ /^[ \t]*(#|$)/) continue
            split(linea, campo)
            ip[campo[1]] = campo[3]
        }
    }
    /^[ \t]*(#|$)/   { next }
    NF != 2          { error("línea mal formada: " $0); next }
    !($2 in ip)      { error("la máquina \"" $2 "\" de " $1 " no está en peers.conf"); next }
    visto[tolower($1)]++ { error("dominio repetido: " $1); next }
    {
        printf "    %s %s:443;\n", tolower($1), ip[$2]
        print ">> [SensorHub Rutas] " $1 " -> " $2 " (" ip[$2] ")" > "/dev/stderr"
    }
    END { exit fallo }
' "$RUTAS_FILE" > "$SALIDA"
