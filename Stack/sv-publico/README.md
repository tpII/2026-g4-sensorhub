# Servidor público: cliente Tailscale + ruteo por SNI

Esta carpeta se copia y se levanta en el servidor público. No hostea nada: recibe el tráfico TLS en el `443/tcp`, mira el SNI y, según el dominio, lo reenvía sin descifrar por la tailnet a la PC que lo atiende, donde Traefik termina el TLS. Un mismo servidor puede atender a varias PCs, cada una con sus propios dominios. La arquitectura completa, la configuración de Tailscale y la parte de cada PC están en [`../tunel-local/README.md`](../tunel-local/README.md).

| Servicio | Qué hace |
|---|---|
| `tailscale` | Cliente Tailscale en modo kernel (`tag:sv-publico`). Es el dueño del namespace de red y publica los puertos. |
| `nginx` | Comparte el namespace de `tailscale`. Con `ssl_preread` rutea por SNI según `rutas.conf`; un dominio que no está ahí se corta. |

Este cliente corre en modo kernel (con `NET_ADMIN` y `/dev/net/tun`) porque nginx tiene que abrir conexiones hacia la tailnet; en las PCs con servicios corre en modo *userspace*, sin privilegios, porque solo recibe.

## Tabla de rutas

**[`rutas.conf`](rutas.conf.example)**: qué PC atiende cada dominio, por su nombre en la tailnet (su `TS_HOSTNAME`).

```text
# dominio               máquina
mcp.ejemplo.com         leno
mqtt.ejemplo.com        leno
mcp2.ejemplo.com        pc-2
mqtt2.ejemplo.com       pc-2
```

Al arrancar, nginx arma la tabla con `<máquina>.<TS_TAILNET>:443` y resuelve cada nombre con MagicDNS (`100.100.100.100`) en cada conexión. Se valida el formato, que no haya dominios repetidos y que los nombres de máquina sean válidos; si hay un error, el contenedor no levanta y el log dice qué línea corregir.

Qué puede alcanzar este servidor dentro de la tailnet no lo decide esta tabla sino la [política de acceso](tailscale-policy.hujson): solo el `443` de las máquinas con `tag:servicios`. Si se agrega a `rutas.conf` una máquina sin ese tag, la conexión no pasa.

## Puertos

| Puerto | Uso |
|---|---|
| `443/tcp` | Los dominios de `rutas.conf` (nginx) |
| `41641/udp` | Conexiones directas de Tailscale |

El `41641/udp` no es obligatorio: sin él Tailscale funciona igual, pero el tráfico pasa por sus relays (DERP), con más latencia. Con él abierto, las PCs conectan directo a este servidor.

## Requisitos

- Docker con Compose v2.
- `/dev/net/tun` disponible (cualquier Linux actual).
- Un registro `A` en Cloudflare por cada dominio de `rutas.conf` apuntando a esta IP, con la **nube gris** (*DNS only*).
- Una auth key con `tag:sv-publico` y el *Tailnet name* (ver [`../tunel-local/README.md`](../tunel-local/README.md#1-tailscale)).

## Puesta en marcha

```bash
cd sv-publico
cp .env.example .env              # TS_AUTHKEY y TS_TAILNET
cp rutas.conf.example rutas.conf  # dominios
docker compose up -d --build
docker compose logs -f
```

Copiar `rutas.conf` **antes** del primer `up`: si no existe, Docker crea una carpeta vacía con ese nombre en su lugar (borrarla y copiar el archivo). Está en el `.gitignore`, igual que el `.env`.

## Agregar una máquina

1. Levantar el `tunel-local` de la PC nueva con su propio `TS_HOSTNAME` y una auth key con `tag:servicios`.
2. Agregar sus dominios a `rutas.conf` y crear los registros `A` en Cloudflare.
3. Aplicar: `docker compose restart nginx`. Las conexiones abiertas de las demás PCs se cortan y se reconectan solas.

## Verificar

```bash
docker exec sensorhub_ts_publico tailscale status          # toshi y cada PC con servicios (leno, ...)
docker exec sensorhub_ts_publico tailscale ping leno       # "via <ip>:<puerto>" = directo, "via DERP" = relay
docker compose logs nginx                                  # rutas cargadas al arrancar
docker compose logs -f nginx                               # una línea por conexión: sni=... upstream=...
```

Las conexiones con un SNI desconocido aparecen con `upstream=127.0.0.1:1` y `status=502`: son descartadas a propósito.
