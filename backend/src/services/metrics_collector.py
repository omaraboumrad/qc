import json
import time
from typing import Dict, List
from ..utils.docker_exec import DockerExecutor
from ..utils.parsers import (
    parse_tc_class_stats,
    parse_connections,
    parse_interface_name_to_client,
    calculate_bandwidth
)
from ..models.metrics import (
    MetricsSnapshot,
    InterfaceStats,
    DirectionalStats,
    InterfaceClassStats,
    Connection,
    TrafficRule
)


class MetricsCollector:
    """Collect metrics from router container"""

    def __init__(self):
        self.docker = DockerExecutor()
        self.previous_bytes = {}  # Track bytes for bandwidth calculation
        self.previous_timestamps = {}  # Track timestamps for accurate interval calculation
        self.ifb_mapping = self._build_ifb_mapping()

    def _build_ifb_mapping(self) -> Dict[str, str]:
        """
        Build IFB device mapping dynamically based on detected client interfaces.
        Maps each client interface to a unique IFB device.
        """
        from ..utils.parsers import parse_interface_name_to_client

        mapping = {}
        ifb_counter = 1

        # Build mapping for all potential interfaces
        for iface in ['eth0', 'eth1', 'eth2', 'eth3', 'eth4']:
            client = parse_interface_name_to_client(iface)
            if client != 'unknown':
                mapping[iface] = f'ifb{ifb_counter}'
                ifb_counter += 1

        return mapping

    async def collect_tc_stats(self, interface: str) -> Dict:
        """Collect traffic control statistics for an interface"""
        exit_code, output = self.docker.exec_router(f"tc -s class show dev {interface}")

        if exit_code != 0:
            return {}

        classes = parse_tc_class_stats(output)
        class_stats = {}

        for cls in classes:
            class_stats[cls['classid']] = InterfaceClassStats(
                classid=cls['classid'],
                bytes=cls['bytes'],
                packets=cls['packets'],
                drops=cls['drops'],
                overlimits=cls['overlimits'],
                rate=cls.get('rate'),
                ceil=cls.get('ceil')
            )

        return class_stats

    async def collect_directional_stats(self, device: str, direction_key: str) -> DirectionalStats:
        """
        Collect statistics for one direction (downstream or upstream)

        Args:
            device: Device name (eth1-4 for downstream, ifb11-14 for upstream)
            direction_key: Key for previous_bytes tracking (e.g., "eth1_down", "ifb11_up")

        Returns:
            DirectionalStats object
        """
        # Get traffic class stats
        classes = await self.collect_tc_stats(device)

        # Calculate total bytes sent (only from leaf classes to avoid double-counting parent)
        leaf_classes = ['1:10', '1:20', '1:30', '2:10', '2:20', '2:30']
        total_bytes = sum(cls.bytes for classid, cls in classes.items() if classid in leaf_classes)

        # Calculate bandwidth using actual time interval
        current_time = time.time()
        prev_bytes = self.previous_bytes.get(direction_key, total_bytes)
        prev_time = self.previous_timestamps.get(direction_key, current_time)

        bytes_diff = total_bytes - prev_bytes
        time_diff = max(current_time - prev_time, 0.1)  # Minimum 0.1s to avoid division by zero

        self.previous_bytes[direction_key] = total_bytes
        self.previous_timestamps[direction_key] = current_time

        # Calculate bandwidth in Mbps using actual time interval
        bandwidth_mbps = calculate_bandwidth(bytes_diff, time_diff)

        # Calculate totals
        total_packets = sum(cls.packets for cls in classes.values())
        total_drops = sum(cls.drops for cls in classes.values())

        # Calculate utilization (assuming 100 Mbit max)
        max_bandwidth = 100.0  # Mbps
        utilization = min((bandwidth_mbps / max_bandwidth) * 100, 100.0)

        return DirectionalStats(
            bandwidth_mbps=bandwidth_mbps,
            packets_sent=total_packets,
            packets_dropped=total_drops,
            utilization_percent=round(utilization, 2),
            classes=classes
        )

    async def collect_interface_stats(self, interface: str) -> InterfaceStats:
        """
        Collect bidirectional statistics for a single interface

        Returns stats for both downstream (router→client) and upstream (client→router)
        Also includes legacy fields for backward compatibility
        """
        client = parse_interface_name_to_client(interface)

        # Collect downstream stats (physical interface)
        downstream = await self.collect_directional_stats(interface, f"{interface}_down")

        # Collect upstream stats (IFB device)
        upstream = None
        ifb_device = self.ifb_mapping.get(interface)
        if ifb_device:
            try:
                upstream = await self.collect_directional_stats(ifb_device, f"{ifb_device}_up")
            except Exception as e:
                # IFB device may not exist if not configured
                print(f"Could not collect upstream stats for {ifb_device}: {e}")

        return InterfaceStats(
            name=interface,
            client=client,
            # New bidirectional fields
            downstream=downstream,
            upstream=upstream,
            # Legacy fields for backward compatibility (use downstream values)
            bandwidth_mbps=downstream.bandwidth_mbps,
            packets_sent=downstream.packets_sent,
            packets_dropped=downstream.packets_dropped,
            utilization_percent=downstream.utilization_percent,
            classes=downstream.classes
        )

    async def collect_connections(self) -> List[Connection]:
        """Collect active iperf3 connections"""
        # Use ss to get established connections on ports 5201-5204 (one per client)
        # Need to wrap in sh -c for pipe to work
        exit_code, output = self.docker.exec_router(
            ["sh", "-c", "ss -tn state established '( dport = :5201 or sport = :5201 or dport = :5202 or sport = :5202 or dport = :5203 or sport = :5203 or dport = :5204 or sport = :5204 )' | tail -n +2"]
        )

        if exit_code != 0:
            return []

        connections = []
        parsed = parse_connections(output)

        for conn in parsed:
            # Extract client from IP
            remote_ip = conn['remote'].split(':')[0]
            client_map = {
                '10.1.0.10': 'pc1',
                '10.2.0.10': 'pc2',
                '10.3.0.10': 'mb1',
                '10.4.0.10': 'mb2',
            }
            client = client_map.get(remote_ip, 'unknown')

            connections.append(Connection(
                client=client,
                protocol=conn['protocol'],
                local_addr=conn['local'],
                remote_addr=conn['remote'],
                state=conn['state']
            ))

        return connections

    async def collect_active_rules(self) -> List[TrafficRule]:
        """Collect active traffic shaping rules (bidirectional)"""
        import re
        rules = []

        # Check each interface for bidirectional rules
        for interface in ['eth1', 'eth2', 'eth3', 'eth4']:
            client = parse_interface_name_to_client(interface)

            # Get downstream configuration (physical interface, handle 1:30)
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

            # Get upstream configuration (IFB device, handle 2:30)
            upstream_rate = None
            upstream_ceil = None

            ifb_device = self.ifb_mapping.get(interface)
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

            # Create rule with both directions
            if downstream_rate and downstream_ceil:
                rules.append(TrafficRule(
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
                    active=True
                ))

        return rules

    async def collect_all(self) -> MetricsSnapshot:
        """Collect all metrics"""
        interfaces = {}

        # Collect stats for each client interface
        for interface in ['eth1', 'eth2', 'eth3', 'eth4']:
            try:
                stats = await self.collect_interface_stats(interface)
                interfaces[interface] = stats
            except Exception as e:
                print(f"Error collecting stats for {interface}: {e}")

        # Collect connections and rules
        connections = await self.collect_connections()
        rules = await self.collect_active_rules()

        return MetricsSnapshot(
            timestamp=time.time(),
            interfaces=interfaces,
            connections=connections,
            rules=rules
        )
