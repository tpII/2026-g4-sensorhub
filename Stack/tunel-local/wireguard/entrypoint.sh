#!/bin/sh
set -eu

# ==============================================================================
# SensorHub - WireGuard del lado de la PC local (cliente del túnel)
# - Genera wg0.conf a partir de las variables de entorno de .env
# - Aísla el namespace de red (compartido con Traefik) del host:
#     * desde el túnel solo entra 443/tcp (Traefik)
#     * hacia sensorhub_network solo sale a EMQX (1883) y MCP (8000)
#     * el host (gateway del bridge) y toda red privada quedan bloqueados
#     * a internet solo sale el túnel y HTTPS (API de Let's Encrypt)
# ==============================================================================

: "${WG_PRIVATE_KEY:?Falta WG_PRIVATE_KEY en .env}"
: "${WG_PEER_PUBLIC_KEY:?Falta WG_PEER_PUBLIC_KEY en .env}"
: "${WG_ENDPOINT:?Falta WG_ENDPOINT en .env (IP-o-host:puerto del servidor público)}"
WG_ADDRESS="${WG_ADDRESS:-10.13.13.2}"
WG_PEER_ADDRESS="${WG_PEER_ADDRESS:-10.13.13.1}"
WG_ENDPOINT_PORT="${WG_ENDPOINT##*:}"
ALLOWED_PORTS="${ALLOWED_PORTS:-1883,8000}"

# 1. Configuración de WireGuard (solo legible por root)
umask 077
mkdir -p /etc/wireguard
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
PrivateKey = ${WG_PRIVATE_KEY}
Address = ${WG_ADDRESS}/32

[Peer]
PublicKey = ${WG_PEER_PUBLIC_KEY}
Endpoint = ${WG_ENDPOINT}
AllowedIPs = ${WG_PEER_ADDRESS}/32
# La PC local está detrás de NAT: mantiene el túnel abierto desde adentro
PersistentKeepalive = 25
EOF

# 2. Firewall del namespace. Solo se toca la tabla filter: la tabla nat la usa
#    Docker para su DNS interno (127.0.0.11), que pasa por lo.
DOCKER_SUBNET=$(ip -4 -o addr show dev eth0 | awk '{print $4}')
DOCKER_GATEWAY=$(ip -4 route show default | awk '{print $3}')
PRIVATE_NETS="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,169.254.0.0/16"

echo ">> [SensorHub Túnel] Aplicando firewall (red ${DOCKER_SUBNET}, host ${DOCKER_GATEWAY} bloqueado)..."
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
iptables -F INPUT
iptables -F FORWARD
iptables -F OUTPUT

iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i wg0 -s "${WG_PEER_ADDRESS}" -p tcp --dport 443 -j ACCEPT

iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d "${DOCKER_GATEWAY}" -j DROP
iptables -A OUTPUT -o eth0 -d "${DOCKER_SUBNET}" -p tcp -m multiport --dports "${ALLOWED_PORTS}" -j ACCEPT
iptables -A OUTPUT -d "${PRIVATE_NETS}" -j DROP
iptables -A OUTPUT -o eth0 -p udp --dport "${WG_ENDPOINT_PORT}" -j ACCEPT
iptables -A OUTPUT -o eth0 -p tcp --dport 443 -j ACCEPT

# IPv6 no se usa: se bloquea todo (puede no existir si Docker no tiene IPv6)
for chain in INPUT FORWARD OUTPUT; do
    ip6tables -P "$chain" DROP 2>/dev/null || true
done

# 3. Levantar el túnel
echo ">> [SensorHub Túnel] Levantando wg0 en ${WG_ADDRESS} hacia ${WG_ENDPOINT}..."
wg-quick up wg0

trap 'wg-quick down wg0; exit 0' TERM INT
tail -f /dev/null &
wait $!
