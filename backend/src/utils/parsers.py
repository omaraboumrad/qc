import json
import re
from typing import Dict, List, Optional


def parse_tc_class_stats(tc_output: str) -> List[Dict]:
    """
    Parse tc class statistics output

    Example input:
    class htb 1:1 root rate 100Mbit ceil 100Mbit burst 1600b cburst 1600b
     Sent 123456 bytes 1234 pkt (dropped 0, overlimits 0 requeues 0)
    """
    classes = []
    lines = tc_output.strip().split('\n')

    current_class = None
    for line in lines:
        # Match class definition
        class_match = re.match(r'class (\w+) ([\d:]+) .* rate (\S+)(?: ceil (\S+))?', line)
        if class_match:
            current_class = {
                'kind': class_match.group(1),
                'classid': class_match.group(2),
                'rate': class_match.group(3),
                'ceil': class_match.group(4) or class_match.group(3),
                'bytes': 0,
                'packets': 0,
                'drops': 0,
                'overlimits': 0
            }
            classes.append(current_class)

        # Match statistics
        if current_class and 'Sent' in line:
            stats_match = re.search(r'Sent (\d+) bytes (\d+) pkt.*dropped (\d+).*overlimits (\d+)', line)
            if stats_match:
                current_class['bytes'] = int(stats_match.group(1))
                current_class['packets'] = int(stats_match.group(2))
                current_class['drops'] = int(stats_match.group(3))
                current_class['overlimits'] = int(stats_match.group(4))

    return classes


def parse_connections(connections_str: str) -> List[Dict]:
    """Parse active connections from ss output"""
    connections = []

    if not connections_str or connections_str.strip() == "":
        return connections

    # Parse ss -tn output format: Recv-Q Send-Q Local Remote
    # Example: 0 0 [::ffff:10.1.0.254]:5201 [::ffff:10.1.0.10]:57266
    for line in connections_str.strip().split('\n'):
        parts = line.split()
        if len(parts) >= 4:
            # Extract local and remote addresses, stripping IPv6-mapped prefix if present
            local = parts[2].replace('[::ffff:', '').replace(']', '')
            remote = parts[3].replace('[::ffff:', '').replace(']', '')

            connections.append({
                'protocol': 'TCP',  # ss -tn always shows TCP
                'state': 'ESTABLISHED',  # filtered by state established
                'local': local,
                'remote': remote
            })

    return connections


def calculate_bandwidth(bytes_sent: int, duration_sec: float = 1.0) -> float:
    """Calculate bandwidth in Mbps"""
    bits = bytes_sent * 8
    mbps = (bits / duration_sec) / 1_000_000
    return round(mbps, 2)


_interface_cache = None

def _detect_interface_mapping():
    """Detect interface to client mapping by querying router IPs"""
    from ..utils.docker_exec import DockerExecutor

    docker = DockerExecutor()
    mapping = {}

    # Get IP addresses for each interface
    for iface in ['eth0', 'eth1', 'eth2', 'eth3', 'eth4']:
        exit_code, output = docker.exec_router(f"ip -4 addr show {iface}")
        if exit_code != 0:
            continue

        # Extract IP address
        match = re.search(r'inet ([\d.]+)/', output)
        if not match:
            continue

        ip = match.group(1)

        # Map IP to client
        ip_to_client = {
            '10.1.0.254': 'pc1',
            '10.2.0.254': 'pc2',
            '10.3.0.254': 'mb1',
            '10.4.0.254': 'mb2',
        }

        if ip in ip_to_client:
            mapping[iface] = ip_to_client[ip]

    return mapping

def parse_interface_name_to_client(interface: str) -> str:
    """Map interface name to client name (auto-detected)"""
    global _interface_cache

    # Cache the mapping to avoid querying router on every call
    if _interface_cache is None:
        _interface_cache = _detect_interface_mapping()

    return _interface_cache.get(interface, 'unknown')
