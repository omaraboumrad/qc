import json
import time
from typing import Dict, List, Optional
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
from .database import DatabaseService


class MetricsCollector:
    """Collect metrics from router container - now supports dynamic devices"""

    def __init__(self, db_service: Optional[DatabaseService] = None):
        self.docker = DockerExecutor()
        self.previous_bytes = {}  # Track bytes for bandwidth calculation
        self.previous_timestamps = {}  # Track timestamps for accurate interval calculation
        self.db = db_service or DatabaseService(db_path="qc.db", echo=False)
        self._owns_db = db_service is None

    def close(self):
        """Close database connection if we own it."""
        if self._owns_db and self.db:
            self.db.close()

    def _get_running_devices(self):
        """Get all running devices from active clusters."""
        return self.db.get_all_active_cluster_devices()

    def _build_device_mappings(self):
        """
        Build device mappings dynamically from database.

        Returns:
            Tuple of (interface_to_device, ip_to_device, interface_to_ifb)
        """
        devices = self._get_running_devices()

        interface_to_device = {}
        ip_to_device = {}
        interface_to_ifb = {}

        for device in devices:
            if device.status == 'running' and device.interface_name:
                interface_to_device[device.interface_name] = device
                ip_to_device[device.ip_address] = device

                if device.ifb_device:
                    interface_to_ifb[device.interface_name] = device.ifb_device

        return interface_to_device, ip_to_device, interface_to_ifb

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

    async def collect_interface_stats(self, interface: str, device_name: str, ifb_device: Optional[str] = None) -> InterfaceStats:
        """
        Collect bidirectional statistics for a single interface

        Args:
            interface: Router interface name (e.g., eth5)
            device_name: Device name from database
            ifb_device: IFB device name for upstream (optional)

        Returns stats for both downstream (router→client) and upstream (client→router)
        Also includes legacy fields for backward compatibility
        """
        # Collect downstream stats (physical interface)
        downstream = await self.collect_directional_stats(interface, f"{interface}_down")

        # Collect upstream stats (IFB device)
        upstream = None
        if ifb_device:
            try:
                upstream = await self.collect_directional_stats(ifb_device, f"{ifb_device}_up")
            except Exception as e:
                # IFB device may not exist if not configured
                print(f"Could not collect upstream stats for {ifb_device}: {e}")

        return InterfaceStats(
            name=interface,
            client=device_name,
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
        """Collect active iperf3 connections - now with dynamic device lookup"""
        # Use ss to get established connections on iperf3 ports
        exit_code, output = self.docker.exec_router(
            ["sh", "-c", "ss -tn state established '( dport >= :5201 and dport <= :5210 )' | tail -n +2"]
        )

        if exit_code != 0:
            return []

        # Build IP to device mapping from database
        _, ip_to_device, _ = self._build_device_mappings()

        connections = []
        parsed = parse_connections(output)

        for conn in parsed:
            # Extract client from IP
            remote_ip = conn['remote'].split(':')[0]

            # Look up device by IP
            device = ip_to_device.get(remote_ip)
            client = device.name if device else 'unknown'

            connections.append(Connection(
                client=client,
                protocol=conn['protocol'],
                local_addr=conn['local'],
                remote_addr=conn['remote'],
                state=conn['state']
            ))

        return connections

    async def collect_active_rules(self) -> List[TrafficRule]:
        """Collect active traffic shaping rules (bidirectional) - now with dynamic devices"""
        import re
        rules = []

        # Get device mappings from database
        interface_to_device, _, interface_to_ifb = self._build_device_mappings()

        # Check each running device interface for bidirectional rules
        for interface, device in interface_to_device.items():
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

            ifb_device = interface_to_ifb.get(interface)
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
                    client=device.name,
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
        """Collect all metrics - now dynamically based on running devices"""
        interfaces = {}

        # Get device mappings from database
        interface_to_device, _, interface_to_ifb = self._build_device_mappings()

        # Collect stats for each running device interface
        for interface, device in interface_to_device.items():
            try:
                ifb_device = interface_to_ifb.get(interface)
                stats = await self.collect_interface_stats(interface, device.name, ifb_device)
                interfaces[interface] = stats
            except Exception as e:
                print(f"Error collecting stats for {interface} ({device.name}): {e}")

        # Collect connections and rules
        connections = await self.collect_connections()
        rules = await self.collect_active_rules()

        return MetricsSnapshot(
            timestamp=time.time(),
            interfaces=interfaces,
            connections=connections,
            rules=rules
        )
