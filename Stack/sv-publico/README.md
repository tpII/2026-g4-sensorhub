# Servidor público: servidor WireGuard + ruteo por SNI

Esta carpeta se copia y se levanta en el servidor público. No hostea nada: recibe el tráfico TLS en el `443/tcp`, mira el SNI y, según el dominio, lo reenvía sin descifrar por el túnel WireGuard a la máquina que lo atiende, donde Traefik termina el TLS. Un mismo servidor puede atender a varias máquinas, cada una con sus propios dominios. La arquitectura completa y la parte de cada máquina están en [`../tunel-local/README.md`](../tunel-local/README.md).

| Servicio | Qué hace |
|---|---|
| `wireguard` | Servidor del túnel (`10.13.13.1`, `51820/udp`), con un peer por línea de `peers.conf`. Es el dueño del namespace de red y publica los puertos. |
| `nginx` | Comparte el namespace de `wireguard`. Con `ssl_preread` rutea por SNI según `rutas.conf`; un dominio que no está ahí se corta. |

## Las dos tablas

**[`peers.conf`](peers.conf.example)**: qué máquinas se conectan. Una línea por máquina: nombre, clave pública y su IP en el túnel.

```text
# nombre    clave_pública                                   ip
pc-local    <clave pública de pc-local>                     10.13.13.2
pc-2        <clave pública de pc-2>                         10.13.13.3
```

**[`rutas.conf`](rutas.conf.example)**: qué máquina atiende cada dominio.

```text
# dominio               máquina
mcp.ejemplo.com         pc-local
mqtt.ejemplo.com        pc-local
mcp2.ejemplo.com        pc-2
mqtt2.ejemplo.com       pc-2
```

La **identidad de cada máquina es su clave pública**; la IP la asigna este archivo. WireGuard ata cada IP a su clave: lo que llegue con la clave de `pc-2` desde `10.13.13.2` se descarta, y lo que el servidor manda a `10.13.13.2` solo se puede descifrar con la clave de `pc-local`. Una máquina no puede quedarse con el tráfico de otra configurándose una IP ajena.

Al arrancar se valida todo: nombres, claves o IPs repetidas en `peers.conf`, dominios repetidos o máquinas inexistentes en `rutas.conf`. Si hay un error, el contenedor no levanta y el log dice qué línea corregir.

Las máquinas no se ven entre sí por el túnel: el servidor no reenvía tráfico entre peers y solo abre conexiones al `443` de cada una.

## Puertos

| Puerto | Uso |
|---|---|
| `443/tcp` | Los dominios de `rutas.conf` (nginx) |
| `51820/udp` | Túnel WireGuard (lo inicia cada máquina) |

Ambos tienen que estar abiertos en el router/firewall de este servidor. Para usar otro puerto UDP, cambiar `WG_LISTEN_PORT` acá y el puerto de `WG_ENDPOINT` en cada máquina.

## Requisitos

- Docker con Compose v2.
- Kernel Linux ≥ 5.6 (WireGuard viene incluido; `lsmod | grep wireguard` o `modprobe wireguard`).
- Un registro `A` en Cloudflare por cada dominio de `rutas.conf` apuntando a esta IP, con la **nube gris** (*DNS only*).

## Puesta en marcha

```bash
cd sv-publico
cp .env.example .env              # clave privada del servidor
cp peers.conf.example peers.conf  # máquinas
cp rutas.conf.example rutas.conf  # dominios
docker compose up -d --build
docker compose logs -f
```

Copiar `peers.conf` y `rutas.conf` **antes** del primer `up`: si no existen, Docker crea carpetas vacías con esos nombres en su lugar (borrarlas y copiar los archivos). Los dos están en el `.gitignore`, igual que el `.env`.

Las claves se generan con:

```bash
docker run --rm alpine:3.20 sh -c 'apk add -q wireguard-tools && k=$(wg genkey) && echo "privada: $k" && echo "pública: $(echo $k | wg pubkey)"'
```

La **privada de este servidor** va en `.env`; su **pública** va en el `.env` de cada máquina (`WG_PEER_PUBLIC_KEY`). La **pública de cada máquina** va en `peers.conf`.

## Agregar una máquina

1. Generar sus claves y agregarla a `peers.conf` con una IP libre (por ejemplo `pc-2 <clave pública> 10.13.13.3`).
2. Agregar sus dominios a `rutas.conf` y crear los registros `A` en Cloudflare.
3. Aplicar: `docker compose up -d --force-recreate` (recrea los dos contenedores; las conexiones abiertas de las demás máquinas se cortan y se reconectan solas).
4. En la máquina nueva, levantar su `tunel-local` con `WG_ADDRESS=10.13.13.3`, sus dominios y la clave pública de este servidor.

Para cambiar solo dominios de máquinas existentes alcanza con `docker compose restart nginx`.

## Verificar

```bash
docker exec sensorhub_wg_publico wg show   # un peer por máquina, con su "latest handshake"
docker compose logs wireguard nginx        # peers y rutas cargadas al arrancar
docker compose logs -f nginx               # una línea por conexión: sni=... upstream=...
```

Las conexiones con un SNI desconocido aparecen con `upstream=127.0.0.1:1` y `status=502`: son descartadas a propósito.
