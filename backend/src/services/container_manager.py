"""
Container Manager Service - Dynamic Docker container lifecycle management.

Handles creation, destruction, and management of client containers and networks.
"""
import docker
import re
import time
from typing import List, Dict, Tuple, Optional
from ..models.database import Device


class ContainerManager:
    """
    Manages dynamic container lifecycle for QC network traffic shaping.

    Responsibilities:
    - Create/destroy client containers
    - Create/destroy isolated Docker networks
    - Attach router to networks (creates new interfaces)
    - Detect router interface names
    - Initialize traffic control on new interfaces
    """

    def __init__(self):
        """Initialize Docker client and get router container reference."""
        self.client = docker.from_env()
        try:
            self.router_container = self.client.containers.get("router")
        except docker.errors.NotFound:
            raise RuntimeError("Router container not found. Please start infrastructure first.")

    def create_device_container(self, device: Device) -> Tuple[bool, str]:
        """
        Create container and network for a device.

        Steps:
        1. Create Docker bridge network
        2. Attach router to network (creates new interface)
        3. Create client container on network
        4. Detect router interface name
        5. Initialize traffic control on new interface

        Args:
            device: Device instance with network configuration

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        try:
            # Step 1: Create isolated Docker network
            print(f"Creating network {device.network_name} ({device.network_subnet})...")
            network = self._create_network(device)
            if not network:
                return False, "Failed to create network"

            # Step 2: Attach router to network (creates new interface on router)
            print(f"Attaching router to network {device.network_name}...")
            try:
                network.connect(
                    self.router_container,
                    ipv4_address=device.router_ip
                )
            except docker.errors.APIError as e:
                error_str = str(e).lower()
                if "already attached" in error_str or "already exists in network" in error_str:
                    print(f"  ℹ️  Router already attached to network")
                else:
                    return False, f"Failed to attach router to network: {e}"

            # Wait for interface to be created
            time.sleep(1)

            # Step 3: Detect router interface for this network
            print(f"Detecting router interface for {device.router_ip}...")
            interface_name = self._detect_router_interface(device.router_ip)
            if not interface_name:
                return False, f"Failed to detect router interface for IP {device.router_ip}"

            print(f"Router interface detected: {interface_name}")

            # Step 4: Initialize traffic control on new interface
            print(f"Initializing traffic control on {interface_name}...")
            tc_success = self._init_traffic_control(interface_name)
            if not tc_success:
                return False, f"Failed to initialize traffic control on {interface_name}"

            # Step 5: Create client container
            print(f"Creating container {device.container_name}...")
            container = self._create_container(device)
            if not container:
                return False, "Failed to create container"

            print(f"✅ Successfully created device: {device.name}")
            return True, interface_name  # Return interface name for device status update

        except docker.errors.APIError as e:
            return False, f"Docker API error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    def destroy_device_container(self, device: Device) -> Tuple[bool, str]:
        """
        Destroy container and network for a device.

        Steps:
        1. Stop and remove client container
        2. Teardown traffic control on router interface
        3. Disconnect router from network
        4. Remove network

        Args:
            device: Device instance

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        errors = []

        try:
            # Step 1: Remove client container
            print(f"Removing container {device.container_name}...")
            try:
                container = self.client.containers.get(device.container_name)
                container.stop(timeout=5)
                container.remove()
                print(f"  ✅ Container removed")
            except docker.errors.NotFound:
                print(f"  ℹ️  Container not found (already removed)")
            except Exception as e:
                errors.append(f"Container removal failed: {e}")

            # Step 2: Teardown traffic control (if interface exists)
            if device.interface_name:
                print(f"Tearing down traffic control on {device.interface_name}...")
                try:
                    self._teardown_traffic_control(device.interface_name)
                    print(f"  ✅ Traffic control removed")
                except Exception as e:
                    errors.append(f"TC teardown failed: {e}")

            # Step 3: Disconnect router from network
            print(f"Disconnecting router from network {device.network_name}...")
            try:
                network = self.client.networks.get(device.network_name)
                network.disconnect(self.router_container, force=True)
                print(f"  ✅ Router disconnected")
            except docker.errors.NotFound:
                print(f"  ℹ️  Network not found (already removed)")
            except Exception as e:
                errors.append(f"Router disconnect failed: {e}")

            # Step 4: Remove network
            print(f"Removing network {device.network_name}...")
            try:
                network = self.client.networks.get(device.network_name)
                network.remove()
                print(f"  ✅ Network removed")
            except docker.errors.NotFound:
                print(f"  ℹ️  Network not found (already removed)")
            except Exception as e:
                errors.append(f"Network removal failed: {e}")

            if errors:
                return False, "; ".join(errors)

            print(f"✅ Successfully destroyed device: {device.name}")
            return True, ""

        except Exception as e:
            return False, f"Unexpected error: {str(e)}"

    def _create_network(self, device: Device) -> Optional[docker.models.networks.Network]:
        """
        Create Docker bridge network for device.

        Args:
            device: Device instance with network configuration

        Returns:
            Network instance or None on failure
        """
        try:
            # Check if network already exists
            try:
                existing_network = self.client.networks.get(device.network_name)
                print(f"  ℹ️  Network {device.network_name} already exists, reusing")
                return existing_network
            except docker.errors.NotFound:
                pass

            # Create new network
            # Note: Don't specify gateway in IPAM - let Docker auto-assign .1
            # We'll manually connect router with the .254 address
            network = self.client.networks.create(
                name=device.network_name,
                driver="bridge",
                ipam=docker.types.IPAMConfig(
                    pool_configs=[
                        docker.types.IPAMPool(
                            subnet=device.network_subnet
                            # No gateway specified - Docker will use .1
                        )
                    ]
                ),
                check_duplicate=True
            )
            print(f"  ✅ Network created: {device.network_name}")
            return network

        except docker.errors.APIError as e:
            print(f"  ❌ Network creation failed: {e}")
            return None

    def _create_container(self, device: Device) -> Optional[docker.models.containers.Container]:
        """
        Create client container for device.

        Args:
            device: Device instance

        Returns:
            Container instance or None on failure
        """
        try:
            # Check if container already exists
            try:
                existing_container = self.client.containers.get(device.container_name)
                print(f"  ℹ️  Container {device.container_name} already exists")
                if existing_container.status != 'running':
                    existing_container.start()
                return existing_container
            except docker.errors.NotFound:
                pass

            # Create new container
            # Note: Can't use networks parameter in run(), need to connect after creation
            container = self.client.containers.run(
                image="qc-client:latest",  # Built from clients/Dockerfile
                name=device.container_name,
                hostname=device.name,
                detach=True,
                environment={
                    "ROUTER_IP": device.router_ip
                },
                restart_policy={"Name": "unless-stopped"},
                remove=False,
                network=device.network_name  # Connect to single network
            )

            # Connect to network with specific IP
            network = self.client.networks.get(device.network_name)
            # Disconnect from default connection and reconnect with specific IP
            try:
                network.disconnect(container, force=True)
            except:
                pass
            network.connect(container, ipv4_address=device.ip_address)
            print(f"  ✅ Container created: {device.container_name}")
            return container

        except docker.errors.ImageNotFound:
            print(f"  ❌ Image 'qc-client:latest' not found. Please build it first.")
            return None
        except docker.errors.APIError as e:
            print(f"  ❌ Container creation failed: {e}")
            return None

    def _detect_router_interface(self, router_ip: str, max_retries: int = 3) -> Optional[str]:
        """
        Detect which router interface has the given IP address.

        Args:
            router_ip: Router IP address to find (e.g., "10.1.0.254")
            max_retries: Number of detection attempts

        Returns:
            Interface name (e.g., "eth5") or None if not found
        """
        for attempt in range(max_retries):
            try:
                # Execute: ip -4 addr show
                result = self.router_container.exec_run("ip -4 addr show")
                if result.exit_code != 0:
                    continue

                output = result.output.decode('utf-8')

                # Parse output to find interface with this IP
                # Format: "    inet 10.1.0.254/24 brd 10.1.0.255 scope global eth5"
                # The interface name appears at the end of the inet line
                for line in output.split('\n'):
                    if 'inet' in line and router_ip in line:
                        # Extract interface name from end of line
                        # e.g., "inet 10.5.0.254/24 brd 10.5.0.255 scope global eth5"
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            # Last part should be the interface name
                            interface = parts[-1]
                            # Verify it looks like an interface name (ethX, enpXsY, etc.)
                            if re.match(r'^(eth|enp|ens)\d+', interface):
                                return interface

                # If not found, wait and retry
                if attempt < max_retries - 1:
                    time.sleep(0.5)

            except Exception as e:
                print(f"  ⚠️  Interface detection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)

        return None

    def _init_traffic_control(self, interface: str) -> bool:
        """
        Initialize HTB traffic control on router interface.

        Creates:
        - Root HTB qdisc (handle 1:)
        - Parent class (1:1) with 10gbit ceiling
        - Default class (1:30) with unlimited rate
        - High/Medium priority classes for future use
        - IFB device for upstream shaping (handle 2:)

        Args:
            interface: Interface name (e.g., "eth5")

        Returns:
            True if successful, False otherwise
        """
        # Extract interface number (eth5 -> 5)
        interface_num_match = re.search(r'\d+', interface)
        if not interface_num_match:
            print(f"  ❌ Could not extract interface number from {interface}")
            return False

        interface_num = interface_num_match.group()
        ifb_device = f"ifb{interface_num}"

        commands = [
            # Downstream (physical interface) - router → client
            f"tc qdisc add dev {interface} root handle 1: htb default 30",
            f"tc class add dev {interface} parent 1: classid 1:1 htb rate 10gbit",
            f"tc class add dev {interface} parent 1:1 classid 1:10 htb rate 50mbit ceil 100mbit prio 1",
            f"tc class add dev {interface} parent 1:1 classid 1:20 htb rate 30mbit ceil 80mbit prio 2",
            f"tc class add dev {interface} parent 1:1 classid 1:30 htb rate 10gbit ceil 10gbit prio 3",

            # Upstream (IFB device) - client → router
            # Load IFB module and create device
            f"modprobe ifb numifbs=32",
            f"ip link add {ifb_device} type ifb 2>/dev/null || true",
            f"ip link set {ifb_device} up",

            # Redirect ingress traffic to IFB for shaping
            f"tc qdisc add dev {interface} ingress",
            f"tc filter add dev {interface} parent ffff: protocol ip u32 match u32 0 0 flowid 1:1 action mirred egress redirect dev {ifb_device}",

            # Set up HTB on IFB device
            f"tc qdisc add dev {ifb_device} root handle 2: htb default 30",
            f"tc class add dev {ifb_device} parent 2: classid 2:1 htb rate 10gbit",
            f"tc class add dev {ifb_device} parent 2:1 classid 2:10 htb rate 50mbit ceil 100mbit prio 1",
            f"tc class add dev {ifb_device} parent 2:1 classid 2:20 htb rate 30mbit ceil 80mbit prio 2",
            f"tc class add dev {ifb_device} parent 2:1 classid 2:30 htb rate 10gbit ceil 10gbit prio 3",
        ]

        for cmd in commands:
            result = self.router_container.exec_run(f"sh -c '{cmd}'")
            if result.exit_code != 0:
                # Some errors are acceptable (e.g., device already exists)
                if "File exists" not in result.output.decode('utf-8', errors='ignore'):
                    output = result.output.decode('utf-8', errors='ignore')
                    if output.strip():  # Only log non-empty errors
                        print(f"  ⚠️  Command warning: {cmd[:50]}... -> {output[:100]}")

        print(f"  ✅ Traffic control initialized on {interface} (upstream: {ifb_device})")
        return True

    def _teardown_traffic_control(self, interface: str) -> bool:
        """
        Remove traffic control from router interface.

        Args:
            interface: Interface name (e.g., "eth5")

        Returns:
            True if successful, False otherwise
        """
        interface_num_match = re.search(r'\d+', interface)
        if interface_num_match:
            interface_num = interface_num_match.group()
            ifb_device = f"ifb{interface_num}"
        else:
            ifb_device = None

        commands = [
            # Remove root qdisc (removes all classes automatically)
            f"tc qdisc del dev {interface} root 2>/dev/null || true",
            f"tc qdisc del dev {interface} ingress 2>/dev/null || true",
        ]

        if ifb_device:
            commands.extend([
                f"tc qdisc del dev {ifb_device} root 2>/dev/null || true",
                f"ip link set {ifb_device} down 2>/dev/null || true",
                f"ip link del {ifb_device} 2>/dev/null || true",
            ])

        for cmd in commands:
            self.router_container.exec_run(f"sh -c '{cmd}'")

        return True

    def get_running_containers(self) -> List[Dict]:
        """
        Get all running QC client containers.

        Returns:
            List of container info dicts
        """
        containers = self.client.containers.list(filters={
            "name": "qc_*"
        })

        return [
            {
                "name": c.name,
                "status": c.status,
                "id": c.id[:12],
                "created": c.attrs['Created']
            }
            for c in containers
        ]

    def kill_all_client_containers(self) -> Tuple[int, List[str]]:
        """
        Stop and remove all QC client containers (emergency shutdown).

        Returns:
            Tuple of (count: int, errors: List[str])
        """
        print("\n🛑 Killing all QC client containers...")

        containers = self.client.containers.list(
            all=True,
            filters={"name": "qc_*"}
        )

        count = 0
        errors = []

        for container in containers:
            try:
                print(f"  Stopping {container.name}...")
                container.stop(timeout=5)
                container.remove()
                count += 1
                print(f"    ✅ Removed")
            except Exception as e:
                error_msg = f"{container.name}: {str(e)}"
                errors.append(error_msg)
                print(f"    ❌ {error_msg}")

        print(f"\n✅ Removed {count} containers")
        if errors:
            print(f"⚠️  {len(errors)} errors occurred")

        return count, errors
