import json
from typing import Dict, List
from ..utils.docker_exec import DockerExecutor
from ..models.rules import BandwidthRule, RuleConfig


class RouterManager:
    """Manage traffic shaping rules on the router"""

    def __init__(self):
        self.docker = DockerExecutor()
        self._build_mappings()

    def _build_mappings(self):
        """Build dynamic interface mappings based on detected IPs"""
        from ..utils.parsers import parse_interface_name_to_client

        # Build client-to-interface mapping
        self.CLIENT_TO_INTERFACE = {}
        self.INTERFACE_TO_CLIENT = {}

        for iface in ['eth0', 'eth1', 'eth2', 'eth3', 'eth4']:
            client = parse_interface_name_to_client(iface)
            if client != 'unknown':
                self.CLIENT_TO_INTERFACE[client] = iface
                self.INTERFACE_TO_CLIENT[iface] = client

        # Build IFB mapping (same as metrics_collector)
        self.IFB_MAPPING = {}
        ifb_counter = 1
        for iface in ['eth0', 'eth1', 'eth2', 'eth3', 'eth4']:
            client = parse_interface_name_to_client(iface)
            if client != 'unknown':
                self.IFB_MAPPING[iface] = f'ifb{ifb_counter}'
                ifb_counter += 1

    def apply_bandwidth_rule(self, rule: BandwidthRule) -> bool:
        """
        Apply a bandwidth limiting rule (supports both bidirectional and legacy modes)

        Bidirectional mode: Uses downstream_rate/upstream_rate fields
        Legacy mode: Uses rate/ceil fields (applies to downstream only)

        Returns:
            True if successful, False otherwise
        """
        # Determine if using bidirectional or legacy mode
        is_bidirectional = (
            rule.downstream_rate is not None or
            rule.upstream_rate is not None
        )

        if is_bidirectional:
            # Bidirectional mode
            success = True

            # Apply downstream rule (physical interface, handle 1:)
            if rule.downstream_rate and rule.downstream_ceil:
                downstream_cmd = (
                    f"tc class change dev {rule.interface} parent 1:1 "
                    f"classid {rule.class_id} htb rate {rule.downstream_rate} ceil {rule.downstream_ceil}"
                )
                exit_code, output = self.docker.exec_router(downstream_cmd)
                if exit_code != 0:
                    print(f"Failed to apply downstream rule: {output}")
                    success = False

            # Apply upstream rule (IFB device, handle 2:)
            # Note: Upstream may fail if IFB devices aren't available (e.g., on macOS Docker)
            # We don't mark the whole operation as failed if only upstream fails
            if rule.upstream_rate and rule.upstream_ceil:
                ifb_device = self.IFB_MAPPING.get(rule.interface)
                if ifb_device:
                    # Use class_id but with handle 2: instead of 1:
                    upstream_class_id = rule.class_id.replace('1:', '2:')
                    upstream_cmd = (
                        f"tc class change dev {ifb_device} parent 2:1 "
                        f"classid {upstream_class_id} htb rate {rule.upstream_rate} ceil {rule.upstream_ceil}"
                    )
                    exit_code, output = self.docker.exec_router(upstream_cmd)
                    if exit_code != 0:
                        print(f"Warning: Failed to apply upstream rule (IFB may not be available): {output}")
                        # Don't set success = False here - upstream is optional
                else:
                    print(f"Warning: No IFB device found for {rule.interface}")

            return success
        else:
            # Legacy mode - apply to downstream only
            cmd = (
                f"tc class change dev {rule.interface} parent 1:1 "
                f"classid {rule.class_id} htb rate {rule.rate} ceil {rule.ceil}"
            )

            exit_code, output = self.docker.exec_router(cmd)

            if exit_code != 0:
                print(f"Failed to apply rule: {output}")
                return False

            return True

    def save_rules(self, config: RuleConfig) -> bool:
        """
        Save rules configuration to router volume for persistence

        Returns:
            True if successful
        """
        # Convert to JSON format expected by apply_rules.sh
        rules_json = {
            "rules": [
                {
                    "interface": rule.interface,
                    "class": rule.class_id,
                    "rate": rule.rate,
                    "ceil": rule.ceil
                }
                for rule in config.rules
            ]
        }

        # Write to temporary file in router
        json_str = json.dumps(rules_json, indent=2)
        escaped_json = json_str.replace('"', '\\"').replace('\n', '\\n')

        # Use echo with heredoc to write file
        cmd = f'cat > /config/rules/active_rules.json << \'EOF\'\n{json_str}\nEOF'

        exit_code, output = self.docker.exec_router(f'bash -c "{cmd}"')

        if exit_code != 0:
            print(f"Failed to save rules: {output}")
            return False

        return True

    def apply_rule_config(self, config: RuleConfig) -> Dict[str, bool]:
        """
        Apply a complete rule configuration

        Returns:
            Dict mapping rule description to success status
        """
        results = {}

        # Apply each bandwidth rule
        for rule in config.rules:
            success = self.apply_bandwidth_rule(rule)
            rule_name = f"{rule.client} ({rule.interface})"
            results[rule_name] = success

        # Save configuration for persistence
        if all(results.values()):
            save_success = self.save_rules(config)
            results['persistence'] = save_success

        return results

    def delete_rule(self, client: str) -> bool:
        """
        Delete a traffic shaping rule by setting it to unlimited bandwidth
        (Applies to both downstream and upstream)

        Args:
            client: Client name (pc1, pc2, mb1, mb2)

        Returns:
            True if successful, False otherwise
        """
        interface = self.CLIENT_TO_INTERFACE.get(client)
        if not interface:
            print(f"Unknown client: {client}")
            return False

        # Create a bidirectional rule with unlimited bandwidth (1000mbit)
        unlimited_rule = BandwidthRule(
            interface=interface,
            client=client,
            class_id='1:30',
            downstream_rate='1000mbit',
            downstream_ceil='1000mbit',
            upstream_rate='1000mbit',
            upstream_ceil='1000mbit',
            description=f'Unlimited bandwidth for {client}'
        )

        return self.apply_bandwidth_rule(unlimited_rule)

    def reset_to_defaults(self) -> bool:
        """
        Reset traffic shaping to default configuration

        Returns:
            True if successful
        """
        exit_code, output = self.docker.exec_router("/scripts/init_tc.sh")

        if exit_code != 0:
            print(f"Failed to reset to defaults: {output}")
            return False

        # Remove persisted rules file
        self.docker.exec_router("rm -f /config/rules/active_rules.json")

        return True

    def get_current_config(self) -> RuleConfig:
        """
        Get current traffic shaping configuration (bidirectional)

        Returns:
            Current rule configuration with both downstream and upstream rates
        """
        import re
        rules = []

        # Query each interface for bidirectional config
        for interface, client in self.INTERFACE_TO_CLIENT.items():
            # Get downstream config (physical interface, handle 1:30)
            downstream_rate = None
            downstream_ceil = None

            exit_code, output = self.docker.exec_router(f"tc class show dev {interface}")
            if exit_code == 0:
                for line in output.split('\n'):
                    if '1:30' in line:
                        rate_match = re.search(r'rate (\S+)', line)
                        ceil_match = re.search(r'ceil (\S+)', line)
                        if rate_match and ceil_match:
                            downstream_rate = rate_match.group(1)
                            downstream_ceil = ceil_match.group(1)

            # Get upstream config (IFB device, handle 2:30)
            upstream_rate = None
            upstream_ceil = None

            ifb_device = self.IFB_MAPPING.get(interface)
            if ifb_device:
                exit_code, output = self.docker.exec_router(f"tc class show dev {ifb_device}")
                if exit_code == 0:
                    for line in output.split('\n'):
                        if '2:30' in line:
                            rate_match = re.search(r'rate (\S+)', line)
                            ceil_match = re.search(r'ceil (\S+)', line)
                            if rate_match and ceil_match:
                                upstream_rate = rate_match.group(1)
                                upstream_ceil = ceil_match.group(1)

            # Create rule with both directions (or legacy if no IFB)
            if downstream_rate and downstream_ceil:
                rules.append(BandwidthRule(
                    interface=interface,
                    client=client,
                    class_id='1:30',
                    downstream_rate=downstream_rate,
                    downstream_ceil=downstream_ceil,
                    upstream_rate=upstream_rate,
                    upstream_ceil=upstream_ceil,
                    # Legacy fields for backward compatibility
                    rate=downstream_rate,
                    ceil=downstream_ceil,
                    description=f"Current rule for {client}"
                ))

        return RuleConfig(rules=rules, qos_rules=[])
