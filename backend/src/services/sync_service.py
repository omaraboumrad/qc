"""
Sync Service - Reconciles desired state (database) with actual state (Docker).

This is the heart of the dynamic device management system.
"""
from typing import Dict, List, Tuple, Optional, Set
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

from .database import DatabaseService
from .container_manager import ContainerManager
from ..models.database import Device, Cluster


class SyncResult:
    """Result of a sync operation."""
    def __init__(self):
        self.created: List[str] = []
        self.destroyed: List[str] = []
        self.kept: List[str] = []
        self.errors: List[str] = []
        self.updated: List[str] = []

    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "created": self.created,
            "destroyed": self.destroyed,
            "kept": self.kept,
            "updated": self.updated,
            "errors": self.errors,
            "total_operations": len(self.created) + len(self.destroyed),
            "success_count": len(self.created) + len(self.destroyed) - len(self.errors),
            "error_count": len(self.errors)
        }


class SyncPreview:
    """Preview of what sync would do without executing."""
    def __init__(self):
        self.to_create: List[str] = []
        self.to_destroy: List[str] = []
        self.to_keep: List[str] = []

    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "to_create": self.to_create,
            "to_destroy": self.to_destroy,
            "to_keep": self.to_keep,
            "total_changes": len(self.to_create) + len(self.to_destroy)
        }


class SyncService:
    """
    Sync Service - Reconciles desired state with actual state.

    Desired State: Devices in database (active clusters)
    Actual State: Running Docker containers

    The sync operation:
    1. Queries active clusters from database
    2. Queries running QC containers from Docker
    3. Calculates diff (create, destroy, keep)
    4. Executes changes in parallel
    5. Updates database with results
    """

    def __init__(self, db_service: Optional[DatabaseService] = None):
        """
        Initialize sync service.

        Args:
            db_service: Optional database service (creates new one if not provided)
        """
        self.db = db_service or DatabaseService(db_path="qc.db", echo=False)
        self.cm = ContainerManager()
        self._owns_db = db_service is None

    def close(self):
        """Close database connection if we own it."""
        if self._owns_db and self.db:
            self.db.close()

    def get_sync_preview(self, cluster_id: Optional[int] = None) -> SyncPreview:
        """
        Preview what sync would do without executing changes.

        Args:
            cluster_id: Specific cluster to preview, or None for all active clusters

        Returns:
            SyncPreview with lists of devices to create/destroy/keep
        """
        preview = SyncPreview()

        # Get desired state (from database)
        if cluster_id:
            cluster = self.db.get_cluster(cluster_id)
            if not cluster:
                return preview
            desired_devices = self.db.get_cluster_devices(cluster_id)
        else:
            # Multi-cluster: get all devices from all active clusters
            desired_devices = self.db.get_all_active_cluster_devices()

        # Get actual state (from Docker)
        running_containers = self.cm.get_running_containers()
        running_names = {c['name'] for c in running_containers}

        # Build desired container names
        desired_names = {d.container_name for d in desired_devices}

        # Calculate diff
        preview.to_create = sorted(list(desired_names - running_names))
        preview.to_destroy = sorted(list(running_names - desired_names))
        preview.to_keep = sorted(list(desired_names & running_names))

        return preview

    def sync_cluster(self, cluster_id: int) -> SyncResult:
        """
        Sync a specific cluster - reconcile desired vs actual state.

        Args:
            cluster_id: Cluster ID to sync

        Returns:
            SyncResult with details of what was done
        """
        result = SyncResult()

        print(f"\n{'='*60}")
        print(f"SYNCING CLUSTER (ID: {cluster_id})")
        print(f"{'='*60}")

        # 1. Get cluster
        cluster = self.db.get_cluster(cluster_id)
        if not cluster:
            result.errors.append(f"Cluster {cluster_id} not found")
            return result

        print(f"Cluster: {cluster.name} (active: {cluster.active})")

        # 2. Get desired devices from database
        desired_devices = self.db.get_cluster_devices(cluster_id)
        print(f"\nDesired devices: {len(desired_devices)}")
        for device in desired_devices:
            print(f"  - {device.name} ({device.container_name})")

        # 3. Get actual running containers from Docker
        running_containers = self.cm.get_running_containers()
        running_map = {c['name']: c for c in running_containers}
        print(f"\nRunning QC containers: {len(running_containers)}")
        for container in running_containers:
            print(f"  - {container['name']} ({container['status']})")

        # 4. Calculate diff
        desired_map = {d.container_name: d for d in desired_devices}
        desired_names = set(desired_map.keys())
        running_names = set(running_map.keys())

        to_create = desired_names - running_names
        to_destroy = running_names - desired_names
        to_keep = desired_names & running_names

        print(f"\n--- Sync Plan ---")
        print(f"To CREATE: {len(to_create)} containers")
        for name in sorted(to_create):
            print(f"  + {name}")
        print(f"To DESTROY: {len(to_destroy)} containers")
        for name in sorted(to_destroy):
            print(f"  - {name}")
        print(f"To KEEP: {len(to_keep)} containers")
        for name in sorted(to_keep):
            print(f"  = {name}")

        # 5. Execute destroys (in parallel)
        if to_destroy:
            print(f"\n--- Destroying {len(to_destroy)} containers ---")
            self._execute_destroys(to_destroy, running_map, result)

        # 6. Execute creates (in parallel)
        if to_create:
            print(f"\n--- Creating {len(to_create)} containers ---")
            self._execute_creates(to_create, desired_map, result)

        # 7. Update kept containers (ensure status is correct)
        if to_keep:
            print(f"\n--- Updating {len(to_keep)} existing containers ---")
            self._update_kept_devices(to_keep, desired_map, result)

        # 8. Summary
        print(f"\n{'='*60}")
        print(f"SYNC COMPLETE")
        print(f"{'='*60}")
        print(f"✅ Created: {len(result.created)}")
        print(f"✅ Destroyed: {len(result.destroyed)}")
        print(f"✅ Kept: {len(result.kept)}")
        print(f"✅ Updated: {len(result.updated)}")
        if result.errors:
            print(f"❌ Errors: {len(result.errors)}")
            for error in result.errors:
                print(f"   - {error}")

        return result

    def sync_active_clusters(self) -> SyncResult:
        """
        Sync all active clusters (multi-cluster support).

        Returns:
            SyncResult with combined results from all clusters
        """
        result = SyncResult()

        print(f"\n{'='*60}")
        print(f"SYNCING ALL ACTIVE CLUSTERS")
        print(f"{'='*60}")

        # Get all active clusters
        active_clusters = self.db.get_active_clusters()
        if not active_clusters:
            print("No active clusters found.")
            return result

        print(f"Active clusters: {len(active_clusters)}")
        for cluster in active_clusters:
            print(f"  - {cluster.name} (ID: {cluster.id})")

        # Sync each cluster and combine results
        for cluster in active_clusters:
            print(f"\n--- Syncing cluster: {cluster.name} ---")
            cluster_result = self.sync_cluster(cluster.id)

            # Combine results
            result.created.extend(cluster_result.created)
            result.destroyed.extend(cluster_result.destroyed)
            result.kept.extend(cluster_result.kept)
            result.updated.extend(cluster_result.updated)
            result.errors.extend(cluster_result.errors)

        return result

    def _execute_destroys(
        self,
        to_destroy: Set[str],
        running_map: Dict[str, Dict],
        result: SyncResult
    ):
        """
        Destroy containers in parallel.

        Args:
            to_destroy: Set of container names to destroy
            running_map: Map of container name to container info
            result: SyncResult to update
        """
        # Find devices in database for these containers
        devices_to_destroy = []
        orphaned_containers = []

        for container_name in to_destroy:
            device = self.db.get_device_by_container_name(container_name)
            if device:
                devices_to_destroy.append(device)
            else:
                # Orphaned container (not in DB) - still need to destroy it
                print(f"  ⚠️  {container_name} not found in DB (orphaned)")
                orphaned_containers.append(container_name)

        # Destroy devices with DB entries in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {}
            for device in devices_to_destroy:
                future = executor.submit(self._destroy_device_safe, device)
                futures[future] = device.container_name

            for future in as_completed(futures):
                container_name = futures[future]
                try:
                    success, error = future.result()
                    if success:
                        result.destroyed.append(container_name)
                    else:
                        result.errors.append(f"Destroy {container_name}: {error}")
                except Exception as e:
                    result.errors.append(f"Destroy {container_name}: {str(e)}")

        # Destroy orphaned containers (no DB entry, just Docker cleanup)
        for container_name in orphaned_containers:
            try:
                print(f"  Destroying orphaned container: {container_name}")
                container = self.cm.client.containers.get(container_name)
                container.stop(timeout=5)
                container.remove()
                result.destroyed.append(container_name)
                print(f"    ✅ Orphaned container destroyed")
            except Exception as e:
                error_msg = f"Orphaned {container_name}: {str(e)}"
                result.errors.append(error_msg)
                print(f"    ❌ {error_msg}")

    def _execute_creates(
        self,
        to_create: Set[str],
        desired_map: Dict[str, Device],
        result: SyncResult
    ):
        """
        Create containers in parallel.

        Args:
            to_create: Set of container names to create
            desired_map: Map of container name to Device
            result: SyncResult to update
        """
        devices_to_create = [desired_map[name] for name in to_create]

        # Create in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {}
            for device in devices_to_create:
                future = executor.submit(self._create_device_safe, device)
                futures[future] = device.container_name

            for future in as_completed(futures):
                container_name = futures[future]
                try:
                    success, interface_or_error = future.result()
                    if success:
                        result.created.append(container_name)
                    else:
                        result.errors.append(f"Create {container_name}: {interface_or_error}")
                except Exception as e:
                    result.errors.append(f"Create {container_name}: {str(e)}")

    def _update_kept_devices(
        self,
        to_keep: Set[str],
        desired_map: Dict[str, Device],
        result: SyncResult
    ):
        """
        Update devices that are kept (already running).

        Ensures database status is correct and interface is detected.

        Args:
            to_keep: Set of container names to keep
            desired_map: Map of container name to Device
            result: SyncResult to update
        """
        for container_name in to_keep:
            device = desired_map[container_name]

            # If device doesn't have interface_name, detect it
            if not device.interface_name:
                print(f"  Detecting interface for {device.name}...")
                interface_name = self.cm._detect_router_interface(device.router_ip)
                if interface_name:
                    self.db.update_device_status(
                        device_id=device.id,
                        status="running",
                        interface_name=interface_name,
                        ifb_device=f"ifb{interface_name.replace('eth', '')}" if 'eth' in interface_name else None
                    )
                    result.updated.append(container_name)
                    print(f"    ✅ Interface detected: {interface_name}")
            elif device.status != "running":
                # Update status to running
                self.db.update_device_status(
                    device_id=device.id,
                    status="running"
                )
                result.updated.append(container_name)
                print(f"  ✅ Updated status: {device.name} -> running")

            result.kept.append(container_name)

    def _create_device_safe(self, device: Device) -> Tuple[bool, str]:
        """
        Safely create a device container with error handling.

        Creates its own database session for thread safety.

        Args:
            device: Device to create

        Returns:
            Tuple of (success, interface_name_or_error)
        """
        # Create new database service for this thread (thread-safe)
        db = DatabaseService(db_path="qc.db", echo=False)
        cm = ContainerManager()

        try:
            # Update status to 'starting'
            db.update_device_status(device.id, "starting")

            # Create container
            success, result = cm.create_device_container(device)

            if success:
                interface_name = result
                # Update status to 'running'
                db.update_device_status(
                    device_id=device.id,
                    status="running",
                    interface_name=interface_name,
                    ifb_device=f"ifb{interface_name.replace('eth', '')}" if 'eth' in interface_name else None,
                    error_message=None
                )
                return True, interface_name
            else:
                error_message = result
                # Update status to 'error'
                db.update_device_status(
                    device_id=device.id,
                    status="error",
                    error_message=error_message
                )
                return False, error_message

        except Exception as e:
            error_message = str(e)
            db.update_device_status(
                device_id=device.id,
                status="error",
                error_message=error_message
            )
            return False, error_message
        finally:
            db.close()

    def _destroy_device_safe(self, device: Device) -> Tuple[bool, str]:
        """
        Safely destroy a device container with error handling.

        Creates its own database session for thread safety.

        Args:
            device: Device to destroy

        Returns:
            Tuple of (success, error_message)
        """
        # Create new database service for this thread (thread-safe)
        db = DatabaseService(db_path="qc.db", echo=False)
        cm = ContainerManager()

        try:
            # Update status to 'stopping'
            db.update_device_status(device.id, "stopping")

            # Destroy container
            success, error = cm.destroy_device_container(device)

            if success:
                # Update status to 'stopped'
                db.update_device_status(
                    device_id=device.id,
                    status="stopped",
                    interface_name=None,
                    ifb_device=None,
                    error_message=None
                )
                return True, ""
            else:
                # Update status to 'error'
                db.update_device_status(
                    device_id=device.id,
                    status="error",
                    error_message=error
                )
                return False, error

        except Exception as e:
            error_message = str(e)
            db.update_device_status(
                device_id=device.id,
                status="error",
                error_message=error_message
            )
            return False, error_message
        finally:
            db.close()
