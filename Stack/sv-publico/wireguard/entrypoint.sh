#!/bin/sh
set -eu

# ==============================================================================
# SensorHub - WireGuard del lado del servidor público (servidor del túnel)
# - Genera wg0.conf con la clave de .env y un [Peer] por línea de peers.conf
# - Cierra el namespace de red: desde internet solo entra 443/tcp (nginx) y
#   51820/udp (WireGuard); hacia el túnel solo sale 443/tcp a cada máquina.
#   No hay reenvío entre máquinas: ninguna puede alcanzar a otra por el túnel.
# ==============================================================================

: "${WG_PRIVATE_KEY:?Falta WG_PRIVATE_KEY en .env}"
WG_ADDRESS="${WG_ADDRESS:-10.13.13.1}"
WG_LISTEN_PORT="${WG_LISTEN_PORT:-51820}"
PEERS_FILE="/etc/sensorhub/peers.conf"

if [ ! -f "$PEERS_FILE" ]; then
    echo ">> [SensorHub Túnel] Falta peers.conf (copiar peers.conf.example y completarlo)" >&2
    exit 1
fi

# Líneas útiles de peers.conf: "nombre clave ip", sin comentarios ni vacías
peers() {
    grep -v -E '^[[:space:]]*(#|$)' "$PEERS_FILE"
}

# 1. Validar peers.conf: formato y que no se repitan nombres, claves ni IPs
peers | awk -v propia="$WG_ADDRESS" '
    function error(msg) { print ">> [SensorHub Túnel] peers.conf: " msg > "/dev/stderr"; fallo = 1 }
    NF != 3                                   { error("línea mal formada: " $0); next }
    $3 !~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/  { error("IP inválida para " $1 ": " $3) }
    $3 == propia                              { error($1 " usa la IP del servidor (" propia ")") }
    nombres[$1]++                             { error("nombre repetido: " $1) }
    claves[$2]++                              { error("clave repetida en " $1) }
    ips[$3]++                                 { error("IP repetida: " $3 " (" $1 ")") }
    END                                       { exit fallo }
'

# 2. Configuración de WireGuard (solo legible por root)
umask 077
mkdir -p /etc/wireguard
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
PrivateKey = ${WG_PRIVATE_KEY}
Address = ${WG_ADDRESS}/32
ListenPort = ${WG_LISTEN_PORT}
EOF

peers | while read -r nombre clave ip; do
    printf '\n# %s\n[Peer]\nPublicKey = %s\nAllowedIPs = %s/32\n' "$nombre" "$clave" "$ip" >> /etc/wireguard/wg0.conf
done

# 3. Firewall del namespace (compartido con nginx). Solo se toca la tabla filter:
#    la tabla nat la usa Docker para su DNS interno.
echo ">> [SensorHub Túnel] Aplicando firewall..."
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
iptables -F INPUT
iptables -F FORWARD
iptables -F OUTPUT

iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -i eth0 -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -i eth0 -p udp --dport "${WG_LISTEN_PORT}" -j ACCEPT

iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -o eth0 -p udp --sport "${WG_LISTEN_PORT}" -j ACCEPT

peers | while read -r nombre clave ip; do
    echo ">> [SensorHub Túnel] Peer ${nombre}: ${ip}"
    iptables -A OUTPUT -o wg0 -d "${ip}" -p tcp --dport 443 -j ACCEPT
done

# IPv6 no se usa: se bloquea todo (puede no existir si Docker no tiene IPv6)
for chain in INPUT FORWARD OUTPUT; do
    ip6tables -P "$chain" DROP 2>/dev/null || true
done

# 4. Levantar el túnel
echo ">> [SensorHub Túnel] Levantando wg0 en ${WG_ADDRESS}, escuchando en ${WG_LISTEN_PORT}/udp..."
wg-quick up wg0

trap 'wg-quick down wg0; exit 0' TERM INT
tail -f /dev/null &
wait $!
