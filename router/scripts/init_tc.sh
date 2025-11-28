#!/bin/bash
# Initialize bidirectional traffic control using HTB + IFB devices
# - Downstream: HTB on physical interfaces (eth1-eth4) handle 1:
# - Upstream: HTB on IFB devices (ifb11-ifb14) handle 2:

set -e

echo "Initializing bidirectional traffic control..."

# Auto-detect interface to client mapping based on IP addresses
declare -A INTERFACES
declare -A IFB_DEVICES

# Detect which interface has which client network
for iface in eth0 eth1 eth2 eth3 eth4; do
    if ! ip link show "$iface" &>/dev/null; then
        continue
    fi

    # Get the IP address on this interface
    ip_addr=$(ip -4 addr show "$iface" | grep -oP 'inet \K[\d.]+' | head -1)

    if [ -z "$ip_addr" ]; then
        continue
    fi

    # Map IP to client name
    case "$ip_addr" in
        10.1.0.254)
            INTERFACES["$iface"]="pc1"
            IFB_DEVICES["$iface"]="ifb1"
            ;;
        10.2.0.254)
            INTERFACES["$iface"]="pc2"
            IFB_DEVICES["$iface"]="ifb2"
            ;;
        10.3.0.254)
            INTERFACES["$iface"]="mb1"
            IFB_DEVICES["$iface"]="ifb3"
            ;;
        10.4.0.254)
            INTERFACES["$iface"]="mb2"
            IFB_DEVICES["$iface"]="ifb4"
            ;;
        172.20.0.2)
            # Management interface - skip
            continue
            ;;
    esac
done

echo "Detected interface mappings:"
for iface in "${!INTERFACES[@]}"; do
    echo "  $iface → ${INTERFACES[$iface]}"
done
echo ""

# Load IFB module with 4 devices
echo "Loading IFB module..."
modprobe ifb numifbs=4 || {
    echo "Warning: Failed to load IFB module, it may already be loaded"
}

# Bring up IFB devices
echo "Activating IFB devices..."
for ifb in ifb1 ifb2 ifb3 ifb4; do
    if ip link show "$ifb" &>/dev/null; then
        ip link set dev "$ifb" up
        echo "✓ $ifb activated"
    else
        echo "Warning: $ifb not found"
    fi
done

# Initialize traffic control on each interface
for iface in "${!INTERFACES[@]}"; do
    client="${INTERFACES[$iface]}"
    ifb="${IFB_DEVICES[$iface]}"

    # Check if physical interface exists
    if ! ip link show "$iface" &>/dev/null; then
        echo "Warning: Interface $iface not found, skipping..."
        continue
    fi

    echo "Setting up traffic control on $iface ($client)..."

    # ========== DOWNSTREAM (router → client) ==========
    # Physical interface egress with handle 1:

    # Remove any existing qdisc
    tc qdisc del dev "$iface" root 2>/dev/null || true

    # Add root HTB qdisc for downstream
    tc qdisc add dev "$iface" root handle 1: htb default 30

    # Add parent class - 10 Gbit total bandwidth (unlimited)
    tc class add dev "$iface" parent 1: classid 1:1 htb rate 10gbit

    # Add priority classes for downstream
    # High priority (1:10) - 50 Mbit rate, 100 Mbit ceiling
    tc class add dev "$iface" parent 1:1 classid 1:10 htb rate 50mbit ceil 100mbit prio 1

    # Medium priority (1:20) - 30 Mbit rate, 80 Mbit ceiling
    tc class add dev "$iface" parent 1:1 classid 1:20 htb rate 30mbit ceil 80mbit prio 2

    # Default class (1:30) - Unlimited (users set limits as needed)
    tc class add dev "$iface" parent 1:1 classid 1:30 htb rate 10gbit ceil 10gbit prio 3

    # Add filters for downstream ToS marking
    tc filter add dev "$iface" parent 1: protocol ip prio 1 u32 match ip tos 0x10 0xff flowid 1:10
    tc filter add dev "$iface" parent 1: protocol ip prio 2 u32 match ip tos 0x08 0xff flowid 1:20

    echo "✓ Downstream configured on $iface"

    # ========== UPSTREAM (client → router) ==========
    # Use IFB device for ingress shaping

    # Check if IFB device exists
    if ! ip link show "$ifb" &>/dev/null; then
        echo "Warning: IFB device $ifb not found, skipping upstream setup"
        continue
    fi

    # Remove any existing ingress qdisc on physical interface
    tc qdisc del dev "$iface" ingress 2>/dev/null || true

    # Add ingress qdisc to physical interface
    tc qdisc add dev "$iface" handle ffff: ingress

    # Redirect all ingress traffic to IFB device
    tc filter add dev "$iface" parent ffff: protocol ip u32 match u32 0 0 \
        action mirred egress redirect dev "$ifb"

    # Remove any existing qdisc on IFB device
    tc qdisc del dev "$ifb" root 2>/dev/null || true

    # Add root HTB qdisc for upstream (handle 2:)
    tc qdisc add dev "$ifb" root handle 2: htb default 30

    # Add parent class - 10 Gbit total bandwidth (unlimited)
    tc class add dev "$ifb" parent 2: classid 2:1 htb rate 10gbit

    # Add priority classes for upstream
    # High priority (2:10) - 50 Mbit rate, 100 Mbit ceiling
    tc class add dev "$ifb" parent 2:1 classid 2:10 htb rate 50mbit ceil 100mbit prio 1

    # Medium priority (2:20) - 30 Mbit rate, 80 Mbit ceiling
    tc class add dev "$ifb" parent 2:1 classid 2:20 htb rate 30mbit ceil 80mbit prio 2

    # Default class (2:30) - Unlimited (users set limits as needed)
    tc class add dev "$ifb" parent 2:1 classid 2:30 htb rate 10gbit ceil 10gbit prio 3

    # Add filters for upstream ToS marking
    tc filter add dev "$ifb" parent 2: protocol ip prio 1 u32 match ip tos 0x10 0xff flowid 2:10
    tc filter add dev "$ifb" parent 2: protocol ip prio 2 u32 match ip tos 0x08 0xff flowid 2:20

    echo "✓ Upstream configured on $ifb (redirected from $iface)"
done

# Setup iptables mangle table (optional)
echo "Setting up iptables mangle table..."
iptables -t mangle -F

echo ""
echo "Traffic control initialization complete!"
echo ""
echo "Current configuration:"
for iface in "${!INTERFACES[@]}"; do
    if ip link show "$iface" &>/dev/null; then
        echo "=== $iface (${INTERFACES[$iface]}) ==="
        echo "Downstream classes:"
        tc class show dev "$iface" | head -5

        ifb="${IFB_DEVICES[$iface]}"
        if ip link show "$ifb" &>/dev/null; then
            echo "Upstream classes (via $ifb):"
            tc class show dev "$ifb" | head -5
        fi
        echo ""
    fi
done
