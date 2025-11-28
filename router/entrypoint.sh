#!/bin/bash
set -e

echo "Starting router container..."

# Enable IP forwarding (may already be enabled by docker sysctls)
echo "Enabling IP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo "IP forwarding already enabled or managed by sysctls"

# Wait for network interfaces to be ready
echo "Waiting for network interfaces..."
sleep 2

# Check if we have persisted rules, otherwise use defaults
if [ -f /config/rules/active_rules.json ]; then
    echo "Found persisted rules, restoring..."
    /scripts/restore_rules.sh
else
    echo "No persisted rules found, initializing with defaults..."
    /scripts/init_tc.sh
fi

# Start iperf3 servers in daemon mode (one per client)
echo "Starting iperf3 servers on ports 5201-5204..."
iperf3 -s -p 5201 -D  # pc1
iperf3 -s -p 5202 -D  # pc2
iperf3 -s -p 5203 -D  # mb1
iperf3 -s -p 5204 -D  # mb2
echo "All iperf3 servers started"

echo "Router initialization complete!"
echo "Available interfaces:"
ip addr show | grep -E "^[0-9]+: (eth|lo)" || true

echo "Traffic control status:"
tc qdisc show || true

# Keep container running and show logs
echo "Router is ready. Tailing logs..."
tail -f /dev/null
