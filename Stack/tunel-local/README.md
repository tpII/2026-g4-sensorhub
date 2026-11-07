# SensorHub - Exposición a internet con Tailscale Funnel

Un cliente Tailscale en contenedor publica dos servicios del stack, sin IP pública ni servidor intermedio. Tailscale termina el TLS (certificado de Let's Encrypt para `*.ts.net`) y reenvía a los contenedores por la red `sensorhub_network`:

| Servicio | URL pública | Destino |
|---|---|---|
| MCP | `https://<TS_HOSTNAME>.<tailnet>.ts.net/mcp` (443) | `sensorhub_mcp:8000/mcp` |
| MQTTS | `<TS_HOSTNAME>.<tailnet>.ts.net:10000` | `sensorhub_emqx:1883` (TCP plano, solo dentro de Docker) |

Solo se expone `/mcp`; el resto del servidor MCP da `404`. El token del MCP lo verifica el propio servidor, y los dispositivos MQTT se autentican contra EMQX.

## Requisitos (una vez, en el panel de Tailscale)

1. **DNS → HTTPS Certificates → Enable HTTPS.**
2. **Access controls**: pegar [tailscale-policy.hujson](tailscale-policy.hujson) (define el tag `tag:servicios` y le da el atributo `funnel`).
3. **Settings → Keys → Generate auth key**, con el tag `tag:servicios`. Copiarla en `TS_AUTHKEY` de `.env`.

## Puesta en marcha

```bash
cp .env.example .env     # completar TS_AUTHKEY y, si se quiere, TS_HOSTNAME
docker compose up -d     # el stack principal (EMQX y MCP) tiene que estar arriba
docker exec sensorhub_ts_local tailscale funnel status
```

El DNS público y el certificado pueden tardar unos minutos la primera vez (o tras cambiar `TS_HOSTNAME`).

## Probar

```bash
curl -i -X POST https://<nodo>.<tailnet>.ts.net/mcp     # 401: llegó al MCP y pide token
openssl s_client -connect <nodo>.<tailnet>.ts.net:10000 -servername <nodo>.<tailnet>.ts.net
```

## Firmware

`CONFIG_BROKER_HOST` = `<nodo>.<tailnet>.ts.net`, protocolo MQTTS, puerto `10000`. El dispositivo valida el certificado contra la CA raíz ISRG Root X1.

## Notas

- La identidad del nodo vive en el volumen `sensorhub_ts_local_state`. Si se borra, el nodo aparece como una máquina nueva: hace falta una auth key nueva y borrar la vieja del panel.
- Cambiar `TS_HOSTNAME` cambia la URL pública (y hay que actualizar el firmware y los clientes del MCP).
- EMQX ve todas las conexiones como originadas en el contenedor de Tailscale: no usar ACL por IP.
