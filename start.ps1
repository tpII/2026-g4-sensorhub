#Requires -Version 5.1
<#
.SYNOPSIS
    SensorHub - Script de inicio rapido (Windows)

.DESCRIPTION
    Levanta todo el stack de SensorHub con un solo comando.
    Incluye: EMQX, InfluxDB, servidor MCP y MCP Inspector.

.EXAMPLE
    .\start.ps1
    Levanta el stack base.

.EXAMPLE
    .\start.ps1 -Simuladores
    Levanta el stack base + los simuladores de sensores (DHT, PIR, Switch).

.EXAMPLE
    .\start.ps1 -Detener
    Detiene y elimina todos los contenedores.

.EXAMPLE
    .\start.ps1 -Logs
    Muestra los logs de todos los contenedores en tiempo real (Ctrl+C para salir).
#>

param(
    [switch]$Simuladores,
    [switch]$Detener,
    [switch]$Logs
)

# ── Helpers de output ──────────────────────────────────────────────────────────
function titulo { param($t) Write-Host "`n  === $t ===" -ForegroundColor Magenta }
function paso   { param($t) Write-Host "  --> $t" -ForegroundColor Cyan }
function ok     { param($t) Write-Host "  [OK] $t" -ForegroundColor Green }
function alerta { param($t) Write-Host "  [!!] $t" -ForegroundColor Yellow }
function error_ { param($t) Write-Host "  [XX] $t" -ForegroundColor Red; exit 1 }

# ── Rutas del proyecto ─────────────────────────────────────────────────────────
$ROOT      = $PSScriptRoot
$STACK_DIR = Join-Path $ROOT "Stack"
$MCP_DIR   = Join-Path $ROOT "MCP"
$SIM_DIR   = Join-Path $ROOT "Stack\simuladores-mqtt"

# ── Asegurar Docker en PATH ────────────────────────────────────────────────────
function Asegurar-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        $bin = "C:\Program Files\Docker\Docker\resources\bin"
        if (Test-Path $bin) { $env:PATH += ";$bin"; alerta "Docker agregado al PATH de esta sesion" }
        else { error_ "Docker no encontrado. Descargalo en: https://www.docker.com/products/docker-desktop/" }
    }
    $null = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        error_ "Docker Desktop no esta corriendo. Abri la app y espera que el icono de la ballena este en verde."
    }
    ok "Docker $(& docker version --format '{{.Server.Version}}' 2>$null) detectado"
}

# ── Esperar que EMQX este listo ────────────────────────────────────────────────
function Esperar-EMQX {
    paso "Esperando que EMQX inicialice (hasta 60s)..."
    for ($i = 3; $i -le 60; $i += 3) {
        Start-Sleep -Seconds 3
        $ready = docker logs sensorhub_emqx 2>&1 | Select-String "is running now"
        if ($ready) { ok "EMQX listo"; return }
        Write-Host "    $i/60 s..." -ForegroundColor DarkGray
    }
    alerta "EMQX tardo mas de lo esperado, pero continuamos igual."
}

# ── Mostrar estado final ───────────────────────────────────────────────────────
function Mostrar-Estado {
    titulo "Estado de los contenedores"
    docker ps -a --filter "name=sensorhub" --format "{{.Names}}|{{.Status}}" | ForEach-Object {
        $p = $_ -split "\|"
        $nombre = $p[0].PadRight(42)
        if ($p[1] -like "Up*") { Write-Host "  [OK] $nombre $($p[1])" -ForegroundColor Green }
        else                   { Write-Host "  [XX] $nombre $($p[1])" -ForegroundColor Red }
    }
}

# ── Mostrar URLs ───────────────────────────────────────────────────────────────
function Mostrar-URLs {
    Write-Host @"

  ================================================
   EMQX Dashboard   ->  http://localhost:18083
                        user: admin  /  pass: admin

   InfluxDB UI       ->  http://localhost:8086
                        user: admin  /  pass: adminpassword123

   MCP Inspector     ->  http://localhost:6274
                        Conectar a: http://sensorhub_mcp:8000/mcp

   MCP API           ->  http://localhost:8000/mcp
  ================================================

  Otros comandos:
    .\start.ps1 -Simuladores   <- con sensores simulados
    .\start.ps1 -Detener       <- apagar todo
    .\start.ps1 -Logs          <- ver logs en vivo

"@ -ForegroundColor Cyan
}

# ══════════════════════════════════════════════════════════════════════════════
#  MODO: DETENER
# ══════════════════════════════════════════════════════════════════════════════
if ($Detener) {
    titulo "SensorHub - Deteniendo todo"
    Asegurar-Docker
    foreach ($dir in @($SIM_DIR, $MCP_DIR, $STACK_DIR)) {
        if (Test-Path $dir) {
            paso "Deteniendo: $dir"
            Push-Location $dir; docker compose down 2>$null; Pop-Location
        }
    }
    ok "Todo detenido."
    exit 0
}

# ══════════════════════════════════════════════════════════════════════════════
#  MODO: LOGS
# ══════════════════════════════════════════════════════════════════════════════
if ($Logs) {
    titulo "SensorHub - Logs (Ctrl+C para salir)"
    Asegurar-Docker
    $contenedores = @("sensorhub_emqx", "sensorhub_influxdb", "sensorhub_mcp", "sensorhub_mcp_inspector")
    # docker logs solo acepta un contenedor a la vez; lanzamos uno por job y esperamos
    $jobs = $contenedores | ForEach-Object {
        $c = $_
        Start-Job -ScriptBlock {
            param($name)
            $env:PATH += ";C:\Program Files\Docker\Docker\resources\bin"
            & docker logs --follow --tail 30 $name 2>&1 | ForEach-Object { "[$name] $_" }
        } -ArgumentList $c
    }
    try {
        $jobs | Receive-Job -Wait
    } finally {
        $jobs | Stop-Job; $jobs | Remove-Job -Force
    }
    exit 0
}

# ══════════════════════════════════════════════════════════════════════════════
#  MODO: INICIAR (default)
# ══════════════════════════════════════════════════════════════════════════════
titulo "SensorHub - Inicio Rapido"
Asegurar-Docker

# 1. Stack base
paso "Levantando EMQX + InfluxDB..."
Push-Location $STACK_DIR
docker compose up -d
if ($LASTEXITCODE -ne 0) { error_ "Fallo al levantar el Stack base." }
Pop-Location
ok "EMQX + InfluxDB en marcha"

# 2. Esperar EMQX
Esperar-EMQX

# 3. MCP
paso "Levantando MCP Server + Inspector..."
Push-Location $MCP_DIR
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { error_ "Fallo al levantar el MCP." }
Pop-Location
ok "MCP Server + Inspector en marcha"

# 4. Simuladores (opcional)
if ($Simuladores) {
    paso "Levantando simuladores MQTT (DHT, PIR, Switch)..."
    Push-Location $SIM_DIR
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { error_ "Fallo al levantar los simuladores." }
    Pop-Location
    ok "Simuladores en marcha"
}

Mostrar-Estado
Mostrar-URLs

$r = Read-Host "  Abrir los tres paneles en el browser? (s/N)"
if ($r -match "^[sS]$") {
    Start-Process "http://localhost:18083"
    Start-Sleep -Milliseconds 400
    Start-Process "http://localhost:8086"
    Start-Sleep -Milliseconds 400
    Start-Process "http://localhost:6274"
    ok "Paneles abiertos"
}

Write-Host "`n  SensorHub listo! Buena suerte :)`n" -ForegroundColor Green