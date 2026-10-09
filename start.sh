#!/usr/bin/env bash
# =============================================================================
#  SensorHub - Script de inicio rapido (Linux / macOS)
#
#  USO:
#    ./start.sh                  Levanta el stack base
#    ./start.sh --simuladores    Levanta todo + sensores simulados
#    ./start.sh --detener        Detiene y elimina todos los contenedores
#    ./start.sh --logs           Muestra logs en tiempo real (Ctrl+C para salir)
#    ./start.sh --ayuda          Muestra este mensaje
# =============================================================================

set -euo pipefail

# ── Colores ────────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m';  MAGENTA='\033[0;35m'; RESET='\033[0m'

titulo()  { echo -e "\n${MAGENTA}  === $1 ===${RESET}"; }
paso()    { echo -e "${CYAN}  --> $1${RESET}"; }
ok()      { echo -e "${GREEN}  [OK] $1${RESET}"; }
alerta()  { echo -e "${YELLOW}  [!!] $1${RESET}"; }
error_()  { echo -e "${RED}  [XX] $1${RESET}"; exit 1; }

# ── Rutas del proyecto ─────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_DIR="$ROOT/Stack"
MCP_DIR="$ROOT/MCP"
SIM_DIR="$ROOT/Stack/simuladores-mqtt"

# ── Flags ─────────────────────────────────────────────────────────────────────
SIMULADORES=false
DETENER=false
LOGS=false

for arg in "$@"; do
    case "$arg" in
        --simuladores) SIMULADORES=true ;;
        --detener)     DETENER=true ;;
        --logs)        LOGS=true ;;
        --ayuda|-h)
            sed -n '/^#  USO:/,/^# ====/p' "$0" | grep -v "^# ====" | sed 's/^#  \?/  /'
            exit 0
            ;;
        *) error_ "Argumento desconocido: $arg  (usa --ayuda para ver las opciones)" ;;
    esac
done

# ── Verificar Docker ───────────────────────────────────────────────────────────
asegurar_docker() {
    if ! command -v docker &>/dev/null; then
        error_ "Docker no encontrado. Instalalo en: https://docs.docker.com/engine/install/"
    fi
    if ! docker info &>/dev/null; then
        error_ "El daemon de Docker no esta corriendo. Ejecuta: sudo systemctl start docker"
    fi
    ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) detectado"
}

# ── Esperar que EMQX este listo ────────────────────────────────────────────────
esperar_emqx() {
    paso "Esperando que EMQX inicialice (hasta 60s)..."
    for i in $(seq 3 3 60); do
        sleep 3
        if docker logs sensorhub_emqx 2>&1 | grep -q "is running now"; then
            ok "EMQX listo"; return
        fi
        echo "    $i/60 s..."
    done
    alerta "EMQX tardo mas de lo esperado, pero continuamos igual."
}

# ── Mostrar estado ─────────────────────────────────────────────────────────────
mostrar_estado() {
    titulo "Estado de los contenedores"
    docker ps -a --filter "name=sensorhub" --format "{{.Names}}|{{.Status}}" | while IFS='|' read -r nombre estado; do
        printf "  %-42s %s\n" "$nombre" "$estado"
        if [[ "$estado" == Up* ]]; then
            echo -e "${GREEN}  [OK] ${nombre}${RESET}"
        else
            echo -e "${RED}  [XX] ${nombre} - ${estado}${RESET}"
        fi
    done
}

# ── Mostrar URLs ───────────────────────────────────────────────────────────────
mostrar_urls() {
    echo -e "${CYAN}"
    echo "  ================================================"
    echo "   EMQX Dashboard   ->  http://localhost:18083"
    echo "                        user: admin  /  pass: admin"
    echo ""
    echo "   InfluxDB UI       ->  http://localhost:8086"
    echo "                        user: admin  /  pass: adminpassword123"
    echo ""
    echo "   MCP Inspector     ->  http://localhost:6274"
    echo "                        Conectar a: http://sensorhub_mcp:8000/mcp"
    echo ""
    echo "   MCP API           ->  http://localhost:8000/mcp"
    echo "  ================================================"
    echo ""
    echo "  Otros comandos:"
    echo "    ./start.sh --simuladores   <- con sensores simulados"
    echo "    ./start.sh --detener       <- apagar todo"
    echo "    ./start.sh --logs          <- ver logs en vivo"
    echo -e "${RESET}"
}

# ══════════════════════════════════════════════════════════════════════════════
#  MODO: DETENER
# ══════════════════════════════════════════════════════════════════════════════
if $DETENER; then
    titulo "SensorHub - Deteniendo todo"
    asegurar_docker
    for dir in "$SIM_DIR" "$MCP_DIR" "$STACK_DIR"; do
        [ -d "$dir" ] && { paso "Deteniendo: $dir"; cd "$dir" && docker compose down 2>/dev/null || true; }
    done
    ok "Todo detenido."
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  MODO: LOGS
# ══════════════════════════════════════════════════════════════════════════════
if $LOGS; then
    titulo "SensorHub - Logs (Ctrl+C para salir)"
    asegurar_docker
    docker logs --follow --tail 50 sensorhub_emqx sensorhub_influxdb sensorhub_mcp sensorhub_mcp_inspector 2>&1
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  MODO: INICIAR (default)
# ══════════════════════════════════════════════════════════════════════════════
titulo "SensorHub - Inicio Rapido"
asegurar_docker

# 1. Stack base
paso "Levantando EMQX + InfluxDB..."
cd "$STACK_DIR" && docker compose up -d || error_ "Fallo al levantar el Stack base."
ok "EMQX + InfluxDB en marcha"

# 2. Esperar EMQX
esperar_emqx

# 3. MCP
paso "Levantando MCP Server + Inspector..."
cd "$MCP_DIR" && docker compose up -d --build || error_ "Fallo al levantar el MCP."
ok "MCP Server + Inspector en marcha"

# 4. Simuladores (opcional)
if $SIMULADORES; then
    paso "Levantando simuladores MQTT (DHT, PIR, Switch)..."
    cd "$SIM_DIR" && docker compose up -d --build || error_ "Fallo al levantar los simuladores."
    ok "Simuladores en marcha"
fi

mostrar_estado
mostrar_urls

# Abrir browser (si hay xdg-open disponible)
if command -v xdg-open &>/dev/null || command -v open &>/dev/null; then
    read -rp "  Abrir los tres paneles en el browser? (s/N) " resp
    if [[ "$resp" =~ ^[sS]$ ]]; then
        OPENER=$(command -v xdg-open || command -v open)
        $OPENER "http://localhost:18083" 2>/dev/null &
        sleep 0.4
        $OPENER "http://localhost:8086" 2>/dev/null &
        sleep 0.4
        $OPENER "http://localhost:6274" 2>/dev/null &
        ok "Paneles abiertos"
    fi
fi

echo -e "\n${GREEN}  SensorHub listo! Buena suerte :)${RESET}\n"