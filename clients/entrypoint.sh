#!/bin/bash

echo "Starting client container: $(hostname)"

# Wait for network to be ready
sleep 1

# Add default route through router
if [ -n "$ROUTER_IP" ]; then
    echo "Setting default route via $ROUTER_IP..."
    route add default gw "$ROUTER_IP" 2>/dev/null || echo "Route already exists or failed to add"
fi

# Display network configuration
echo "Network configuration:"
ip addr show
echo ""
echo "Routing table:"
ip route show
echo ""

# Test connectivity to router
if [ -n "$ROUTER_IP" ]; then
    echo "Testing connectivity to router ($ROUTER_IP)..."
    ping -c 3 "$ROUTER_IP" || echo "Warning: Cannot ping router"
fi

echo "Client $(hostname) is ready!"

# Keep container running
tail -f /dev/null
