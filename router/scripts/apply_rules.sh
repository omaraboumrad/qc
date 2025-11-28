#!/bin/bash
# Apply traffic shaping rules from JSON configuration

set -e

CONFIG_FILE="$1"

if [ -z "$CONFIG_FILE" ] || [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not specified or not found"
    echo "Usage: $0 <config_file.json>"
    exit 1
fi

echo "Applying traffic shaping rules from $CONFIG_FILE..."

# Parse JSON and apply rules
# Expected format:
# {
#   "rules": [
#     {
#       "interface": "eth1",
#       "class": "1:30",
#       "rate": "20mbit",
#       "ceil": "50mbit"
#     }
#   ]
# }

# Read number of rules
num_rules=$(jq '.rules | length' "$CONFIG_FILE")

echo "Found $num_rules rules to apply"

for ((i=0; i<num_rules; i++)); do
    interface=$(jq -r ".rules[$i].interface" "$CONFIG_FILE")
    class=$(jq -r ".rules[$i].class" "$CONFIG_FILE")
    rate=$(jq -r ".rules[$i].rate" "$CONFIG_FILE")
    ceil=$(jq -r ".rules[$i].ceil" "$CONFIG_FILE")

    # Check if interface exists
    if ! ip link show "$interface" &>/dev/null; then
        echo "Warning: Interface $interface not found, skipping rule $i"
        continue
    fi

    echo "Applying rule $i: $interface class $class -> rate=$rate ceil=$ceil"

    # Apply the rule
    tc class change dev "$interface" parent 1:1 classid "$class" htb rate "$rate" ceil "$ceil"

    if [ $? -eq 0 ]; then
        echo "✓ Rule applied successfully"
    else
        echo "✗ Failed to apply rule"
    fi
done

echo "Rule application complete!"
