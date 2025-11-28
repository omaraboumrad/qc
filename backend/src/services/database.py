"""
Database service for CRUD operations on clusters, devices, and traffic rules.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict, Tuple
from datetime import datetime

from ..models.database import Cluster, Device, TrafficRule, init_db, get_session


class DatabaseService:
    """
    Centralized database operations for clusters, devices, and rules.
    Handles all database interactions with proper session management.
    """

    def __init__(self, db_path: str = "./qc.db", echo: bool = False):
        """
        Initialize database service.

        Args:
            db_path: Path to SQLite database file
            echo: If True, log SQL statements
        """
        self.engine = init_db(f"sqlite:///{db_path}", echo=echo)
        self.session = get_session(self.engine)

    def close(self):
        """Close the database session."""
        if self.session:
            self.session.close()

    # ========== CLUSTER OPERATIONS ==========

    def create_cluster(self, name: str, description: str = "", active: bool = False) -> Cluster:
        """
        Create a new cluster.

        Args:
            name: Unique cluster name
            description: Optional description
            active: Whether cluster should be active initially

        Returns:
            Created Cluster instance

        Raises:
            ValueError: If cluster name already exists
        """
        # Check if cluster with same name exists
        existing = self.session.query(Cluster).filter_by(name=name).first()
        if existing:
            raise ValueError(f"Cluster with name '{name}' already exists")

        cluster = Cluster(name=name, description=description, active=active)
        self.session.add(cluster)
        self.session.commit()
        self.session.refresh(cluster)
        return cluster

    def get_cluster(self, cluster_id: int) -> Optional[Cluster]:
        """Get cluster by ID."""
        return self.session.query(Cluster).get(cluster_id)

    def get_cluster_by_name(self, name: str) -> Optional[Cluster]:
        """Get cluster by name."""
        return self.session.query(Cluster).filter_by(name=name).first()

    def list_clusters(self, active_only: bool = False) -> List[Cluster]:
        """
        List all clusters.

        Args:
            active_only: If True, only return active clusters

        Returns:
            List of Cluster instances
        """
        query = self.session.query(Cluster)
        if active_only:
            query = query.filter_by(active=True)
        return query.order_by(Cluster.created_at.desc()).all()

    def get_active_clusters(self) -> List[Cluster]:
        """
        Get all active clusters (supports multi-cluster).

        Returns:
            List of active Cluster instances
        """
        return self.session.query(Cluster).filter_by(active=True).all()

    def update_cluster(self, cluster_id: int, name: str = None, description: str = None) -> bool:
        """
        Update cluster properties.

        Args:
            cluster_id: Cluster ID to update
            name: New name (optional)
            description: New description (optional)

        Returns:
            True if successful, False if cluster not found
        """
        cluster = self.get_cluster(cluster_id)
        if not cluster:
            return False

        if name is not None:
            # Check name uniqueness
            existing = self.session.query(Cluster).filter_by(name=name).first()
            if existing and existing.id != cluster_id:
                raise ValueError(f"Cluster with name '{name}' already exists")
            cluster.name = name

        if description is not None:
            cluster.description = description

        cluster.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def activate_cluster(self, cluster_id: int) -> bool:
        """
        Activate a cluster (multi-cluster: doesn't deactivate others).

        Args:
            cluster_id: Cluster ID to activate

        Returns:
            True if successful, False if cluster not found
        """
        cluster = self.get_cluster(cluster_id)
        if not cluster:
            return False

        cluster.active = True
        cluster.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def deactivate_cluster(self, cluster_id: int) -> bool:
        """
        Deactivate a cluster.

        Args:
            cluster_id: Cluster ID to deactivate

        Returns:
            True if successful, False if cluster not found
        """
        cluster = self.get_cluster(cluster_id)
        if not cluster:
            return False

        cluster.active = False
        cluster.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def delete_cluster(self, cluster_id: int) -> bool:
        """
        Delete a cluster and all its devices (cascade).

        Args:
            cluster_id: Cluster ID to delete

        Returns:
            True if successful, False if cluster not found
        """
        cluster = self.get_cluster(cluster_id)
        if not cluster:
            return False

        self.session.delete(cluster)
        self.session.commit()
        return True

    # ========== DEVICE OPERATIONS ==========

    def create_device(
        self,
        cluster_id: int,
        name: str,
        device_type: str,
        network_config: Dict[str, str]
    ) -> Device:
        """
        Create a new device in a cluster.

        Args:
            cluster_id: Parent cluster ID
            name: Device name (unique within cluster)
            device_type: Device type (e.g., "pc", "mobile")
            network_config: Dict with keys: subnet, network_name, container_name,
                           device_ip, router_ip

        Returns:
            Created Device instance

        Raises:
            ValueError: If cluster not found or device name exists in cluster
        """
        # Verify cluster exists
        cluster = self.get_cluster(cluster_id)
        if not cluster:
            raise ValueError(f"Cluster with ID {cluster_id} not found")

        # Check if device with same name exists in cluster
        existing = self.session.query(Device).filter_by(
            cluster_id=cluster_id,
            name=name
        ).first()
        if existing:
            raise ValueError(f"Device '{name}' already exists in cluster '{cluster.name}'")

        device = Device(
            cluster_id=cluster_id,
            name=name,
            device_type=device_type,
            network_subnet=network_config["subnet"],
            network_name=network_config["network_name"],
            container_name=network_config["container_name"],
            ip_address=network_config["device_ip"],
            router_ip=network_config["router_ip"],
            status="stopped"
        )

        self.session.add(device)
        self.session.commit()
        self.session.refresh(device)
        return device

    def get_device(self, device_id: int) -> Optional[Device]:
        """Get device by ID."""
        return self.session.query(Device).get(device_id)

    def get_device_by_container_name(self, container_name: str) -> Optional[Device]:
        """Get device by container name."""
        return self.session.query(Device).filter_by(container_name=container_name).first()

    def get_cluster_devices(self, cluster_id: int) -> List[Device]:
        """
        Get all devices in a cluster.

        Args:
            cluster_id: Cluster ID

        Returns:
            List of Device instances
        """
        return self.session.query(Device).filter_by(cluster_id=cluster_id).order_by(Device.created_at).all()

    def get_all_active_cluster_devices(self) -> List[Device]:
        """
        Get all devices from all active clusters.

        Returns:
            List of Device instances from active clusters
        """
        active_clusters = self.get_active_clusters()
        devices = []
        for cluster in active_clusters:
            devices.extend(cluster.devices)
        return devices

    def get_running_devices(self) -> List[Device]:
        """Get all devices with status='running'."""
        return self.session.query(Device).filter_by(status='running').all()

    def update_device_status(
        self,
        device_id: int,
        status: str,
        interface_name: str = None,
        ifb_device: str = None,
        error_message: str = None
    ) -> bool:
        """
        Update device status and optional runtime info.

        Args:
            device_id: Device ID
            status: New status (stopped, starting, running, stopping, error)
            interface_name: Router interface name (e.g., "eth5")
            ifb_device: IFB device name (e.g., "ifb5")
            error_message: Error message if status is 'error'

        Returns:
            True if successful, False if device not found
        """
        device = self.get_device(device_id)
        if not device:
            return False

        device.status = status
        device.last_synced_at = datetime.utcnow()

        if interface_name is not None:
            device.interface_name = interface_name
        if ifb_device is not None:
            device.ifb_device = ifb_device
        if error_message is not None:
            device.error_message = error_message

        device.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def delete_device(self, device_id: int) -> bool:
        """
        Delete a device and its traffic rules (cascade).

        Args:
            device_id: Device ID

        Returns:
            True if successful, False if device not found
        """
        device = self.get_device(device_id)
        if not device:
            return False

        self.session.delete(device)
        self.session.commit()
        return True

    def get_next_available_network(self, cluster_id: int) -> Tuple[int, str]:
        """
        Calculate next available network octet for a cluster.

        Args:
            cluster_id: Cluster ID

        Returns:
            Tuple of (octet, subnet) e.g., (1, "10.1.0.0/24")
        """
        # Get all existing devices across all clusters
        all_devices = self.session.query(Device).all()

        # Extract octets from existing subnets
        used_octets = set()
        for device in all_devices:
            # Parse "10.X.0.0/24" to get X
            parts = device.network_subnet.split('.')
            if len(parts) >= 2:
                try:
                    used_octets.add(int(parts[1]))
                except ValueError:
                    pass

        # Find first available octet (start from 1)
        for octet in range(1, 255):
            if octet not in used_octets:
                return octet, f"10.{octet}.0.0/24"

        raise ValueError("No available network subnets (all 254 networks in use)")

    # ========== TRAFFIC RULE OPERATIONS ==========

    def create_traffic_rule(
        self,
        device_id: int,
        downstream_rate: str = None,
        downstream_ceil: str = None,
        upstream_rate: str = None,
        upstream_ceil: str = None,
        description: str = ""
    ) -> TrafficRule:
        """
        Create a traffic rule for a device.

        Args:
            device_id: Device ID
            downstream_rate: Downstream guaranteed rate (e.g., "20mbit")
            downstream_ceil: Downstream ceiling (e.g., "50mbit")
            upstream_rate: Upstream guaranteed rate
            upstream_ceil: Upstream ceiling
            description: Optional description

        Returns:
            Created TrafficRule instance

        Raises:
            ValueError: If device not found
        """
        device = self.get_device(device_id)
        if not device:
            raise ValueError(f"Device with ID {device_id} not found")

        rule = TrafficRule(
            device_id=device_id,
            downstream_rate=downstream_rate,
            downstream_ceil=downstream_ceil,
            upstream_rate=upstream_rate,
            upstream_ceil=upstream_ceil,
            description=description,
            active=True
        )

        self.session.add(rule)
        self.session.commit()
        self.session.refresh(rule)
        return rule

    def get_device_traffic_rules(self, device_id: int, active_only: bool = True) -> List[TrafficRule]:
        """
        Get traffic rules for a device.

        Args:
            device_id: Device ID
            active_only: If True, only return active rules

        Returns:
            List of TrafficRule instances
        """
        query = self.session.query(TrafficRule).filter_by(device_id=device_id)
        if active_only:
            query = query.filter_by(active=True)
        return query.all()

    def update_traffic_rule(
        self,
        rule_id: int,
        downstream_rate: str = None,
        downstream_ceil: str = None,
        upstream_rate: str = None,
        upstream_ceil: str = None,
        active: bool = None
    ) -> bool:
        """
        Update a traffic rule.

        Args:
            rule_id: Rule ID
            downstream_rate: New downstream rate
            downstream_ceil: New downstream ceiling
            upstream_rate: New upstream rate
            upstream_ceil: New upstream ceiling
            active: Active status

        Returns:
            True if successful, False if rule not found
        """
        rule = self.session.query(TrafficRule).get(rule_id)
        if not rule:
            return False

        if downstream_rate is not None:
            rule.downstream_rate = downstream_rate
        if downstream_ceil is not None:
            rule.downstream_ceil = downstream_ceil
        if upstream_rate is not None:
            rule.upstream_rate = upstream_rate
        if upstream_ceil is not None:
            rule.upstream_ceil = upstream_ceil
        if active is not None:
            rule.active = active

        rule.updated_at = datetime.utcnow()
        self.session.commit()
        return True

    def delete_traffic_rule(self, rule_id: int) -> bool:
        """
        Delete a traffic rule.

        Args:
            rule_id: Rule ID

        Returns:
            True if successful, False if rule not found
        """
        rule = self.session.query(TrafficRule).get(rule_id)
        if not rule:
            return False

        self.session.delete(rule)
        self.session.commit()
        return True
