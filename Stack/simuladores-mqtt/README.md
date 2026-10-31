# Simuladores MQTT

Scripts contenerizados para simular dispositivos IoT (sensores y actuadores) publicando telemetria en EMQX sin requerir hardware fisico real.

---

## Como levantar

Asegurarse de que el stack principal de SensorHub este corriendo (`cd .. && docker compose up -d`). El broker exige usuario y contraseña: copiar `.env.example` a `.env` con las mismas credenciales MQTT de `Stack/.env` (los simuladores de dispositivos usan el usuario de los ESP y el emisor de comandos, el del MCP). Luego:

```bash
# Levantar todos los simuladores (DHT, PIR, Switch y emisor de comandos)
docker compose up --build

# O levantar solo un simulador especifico:
docker compose up --build simulador-dht
docker compose up --build simulador-pir
docker compose up --build simulador-switch
docker compose up --build simulador-switch-commander

# Detener
docker compose down
```