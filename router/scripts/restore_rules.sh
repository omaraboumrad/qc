#!/bin/bash
# Restore persisted traffic shaping rules on container startup

set -e

RULES_FILE="/config/rules/active_rules.json"

if [ ! -f "$RULES_FILE" ]; then
    echo "No persisted rules file found at $RULES_FILE"
    echo "Falling back to default initialization..."
    /scripts/init_tc.sh
    exit 0
fi

echo "Restoring traffic shaping rules from $RULES_FILE..."

# First, initialize traffic control with default structure
/scripts/init_tc.sh

# Then apply the persisted custom rules
/scripts/apply_rules.sh "$RULES_FILE"

echo "Rules restored successfully!"
