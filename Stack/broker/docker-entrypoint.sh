#!/bin/sh
set -e

# ==============================================================================
# SensorHub EMQX Bootstrap Entrypoint
# - Sustituye variables de entorno de .env en las plantillas de configuración
# - Descubre y ensambla automáticamente todas las reglas en rules/*.conf.template
#   sin requerir modificar este script ni emqx.conf al agregar nuevos dispositivos
# ==============================================================================

TEMPLATES_DIR="/opt/emqx/templates" # El entrypoint corre dentro del contenedor, las rutas son internas a emqx.
TARGET_DIR="/opt/emqx/etc"

# Funcion para reemplazar las variables de un archivo .template con los valores de las variables de entorno del contenedor
substitute_vars() {
    sed \
        -e "s|\${EMQX_DASHBOARD__DEFAULT_USERNAME}|${EMQX_DASHBOARD__DEFAULT_USERNAME:-admin}|g" \
        -e "s|\${EMQX_DASHBOARD__DEFAULT_PASSWORD}|${EMQX_DASHBOARD__DEFAULT_PASSWORD:-admin}|g" \
        -e "s|\${INFLUXDB_ADMIN_TOKEN}|${INFLUXDB_ADMIN_TOKEN}|g" \
        -e "s|\${INFLUXDB_ORG}|${INFLUXDB_ORG:-sensorhub}|g" \
        -e "s|\${INFLUXDB_BUCKET}|${INFLUXDB_BUCKET:-sensorhub}|g" \
        "$1" > "$2"
}

# 1. Procesar configuración base
if [ -f "$TEMPLATES_DIR/emqx.conf.template" ]; then
    echo ">> [SensorHub Bootstrap] Procesando configuración base (emqx.conf)..."
    substitute_vars "$TEMPLATES_DIR/emqx.conf.template" "$TARGET_DIR/emqx.conf"
fi

# 2. Procesar dinamicamente todas las reglas de dispositivos
if [ -d "$TEMPLATES_DIR/rules" ]; then
    mkdir -p "$TARGET_DIR/rules"
    # Imprimir un encabezado en emqx.conf para indicar que las reglas de dispositivos se agregan dinámicamente
    echo "" >> "$TARGET_DIR/emqx.conf"
    echo "## ==============================================================================" >> "$TARGET_DIR/emqx.conf"
    echo "## Módulos de Dispositivos (Auto-descubiertos por SensorHub Bootstrap)" >> "$TARGET_DIR/emqx.conf"
    echo "## ==============================================================================" >> "$TARGET_DIR/emqx.conf"

    # busca cada template de regla, le aplica las variables y agrega su include al emqx.conf
    for tmpl in "$TEMPLATES_DIR/rules"/*.conf.template; do
        [ -f "$tmpl" ] || continue
        rule_name=$(basename "$tmpl" .conf.template)
        target_rule="$TARGET_DIR/rules/${rule_name}.conf"

        echo ">> [SensorHub Bootstrap] Compilando regla modular: ${rule_name}..."
        substitute_vars "$tmpl" "$target_rule"

        # Registrar el include nativo en emqx.conf
        echo "include \"rules/${rule_name}.conf\"" >> "$TARGET_DIR/emqx.conf"
    done
fi

echo ">> [SensorHub Bootstrap] Configuración exitosa."

exec /usr/bin/docker-entrypoint.sh "$@"
