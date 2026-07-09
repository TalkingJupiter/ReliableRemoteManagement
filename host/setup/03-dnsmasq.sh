dnf install -y dnsmasq

cat > /etc/dnsmasq.d/telemetry.conf <<EOF
interface=$TELEMETRY_IFACE
bind-interfaces
except-interface=lo
port=0
dhcp-range=$DHCP_RANGE
dhcp-option=3
dhcp-authoritative
EOF

systemctl enable dnsmasq
systemctl restart dnsmasq

firewall-cmd --permenant --zone=internal --add-service=dhcp
firewall-cmd --permenant --zone=internal --add-port=1883/tcp
firewall-cmd --reload
