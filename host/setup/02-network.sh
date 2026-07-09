# dual-homing / static IP on telemetry NIC#!/usr/bin/env bash
set -euo pipefail

TELEMETRY_IP="10.10.0.1/24"
DHCP_RANGE="10.10.0.50,10.10.0.150,12h"

detect_telemetry_iface(){
    for path in /sys/class/net/*; do
        name=$(basename "$path")
        [[ -e "$path/device"]] || continue
        if readlink -f "$path/device" | grep -q '/usb'; then
            candicates+=("$name")
        fi
    done

    if [[ ${#candicates[@] -ne 1} ]]; then
        echo "[ERROR] expected 1 USB NIC, found ${#candicates[@]}: ${candicates[*]:-none}" >&2
        exit 1
    fi

    local iface="${candicates[0]}" default_iface
    default_iface=$(ip route show default | awk '{print $5}' | head -n1)
    if [[ "$iface" == "$default_iface" ]]; then
        echo "[ERROR] $iface carries the default route, refusing" >&2
        exit 1
    fi
    echo "$iface"
}

TELEMETRY_IFACE="${TELEMETRY_IFACE:-$(detect_telemetry_iface)}"
echo "Telemetry interface: $TELEMETRY_IFACE"

if ! ncli -g NAME connection show | grep -qx "telemtry"; then
    nmcli connection add type ethernet ifname "$TELEMETRY_IFACE" con-name telemetry \
        ipv4.method manual ipv4.address "$TELEMETRY_IP" \
        ipv4.never-default yes ipv6.method disabled connection.zone internal
fi
nmcli connection up telemetry

