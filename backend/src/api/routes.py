from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
from ..services.metrics_collector import MetricsCollector
from ..services.router_manager import RouterManager
from ..services.database import DatabaseService
from ..services.sync_service import SyncService
from ..services.container_manager import ContainerManager
from ..utils.docker_exec import DockerExecutor
from ..models.metrics import MetricsSnapshot
from ..models.rules import BandwidthRule, RuleConfig

router = APIRouter()


def sanitize_container_name(name: str) -> str:
    """
    Sanitize a name for use in Docker container/network names.
    Docker requires: [a-zA-Z0-9][a-zA-Z0-9_.-]*

    Args:
        name: Original name (may contain spaces or special characters)

    Returns:
        Sanitized name safe for Docker
    """
    import re

    # Replace spaces with hyphens
    sanitized = name.replace(' ', '-')

    # Remove any characters not in [a-zA-Z0-9_.-]
    sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '', sanitized)

    # Ensure it starts with alphanumeric (remove leading dots/hyphens)
    sanitized = re.sub(r'^[^a-zA-Z0-9]+', '', sanitized)

    # If empty after sanitization, use 'device'
    if not sanitized:
        sanitized = 'device'

    return sanitized


# Service instances
metrics_collector = MetricsCollector()
router_manager = RouterManager()
docker_executor = DockerExecutor()
db_service = DatabaseService(db_path="qc.db", echo=False)
sync_service = SyncService(db_service=db_service)
container_manager = ContainerManager()


class TrafficControlRequest(BaseModel):
    """Request model for traffic control"""
    client: str
    duration: int = 300  # seconds
    bandwidth: str | None = None  # e.g., "50M", "100M" for iperf3 -b flag


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "qc-backend"}


@router.get("/metrics/current", response_model=MetricsSnapshot)
async def get_current_metrics():
    """Get current metrics snapshot (non-streaming)"""
    try:
        metrics = await metrics_collector.collect_all()
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to collect metrics: {str(e)}")


@router.get("/rules", response_model=RuleConfig)
async def get_rules():
    """Get current traffic shaping rules"""
    try:
        config = router_manager.get_current_config()
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get rules: {str(e)}")


@router.post("/rules/apply")
async def apply_rules(config: RuleConfig) -> Dict[str, bool]:
    """
    Apply traffic shaping rules

    Request body should contain RuleConfig with bandwidth rules
    """
    try:
        results = router_manager.apply_rule_config(config)

        # Check if all rules applied successfully
        all_success = all(results.values())

        if not all_success:
            failed = [k for k, v in results.items() if not v]
            raise HTTPException(
                status_code=500,
                detail=f"Failed to apply some rules: {', '.join(failed)}"
            )

        return results

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying rules: {str(e)}")


@router.post("/rules/apply-single")
async def apply_single_rule(rule: BandwidthRule) -> Dict[str, Any]:
    """Apply a single bandwidth rule"""
    try:
        success = router_manager.apply_bandwidth_rule(rule)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply rule")

        return {
            "status": "success",
            "message": f"Rule applied to {rule.client} ({rule.interface})",
            "rule": {
                "client": rule.client,
                "rate": rule.rate,
                "ceil": rule.ceil
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rules/reset")
async def reset_rules() -> Dict[str, str]:
    """Reset all traffic shaping rules to defaults"""
    try:
        success = router_manager.reset_to_defaults()

        if not success:
            raise HTTPException(status_code=500, detail="Failed to reset rules")

        return {
            "status": "success",
            "message": "Traffic shaping rules reset to defaults"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{client}")
async def delete_rule(client: str) -> Dict[str, str]:
    """Delete a traffic shaping rule (set to unlimited bandwidth)"""
    # No validation needed - accept any client name from dynamic devices
    try:
        success = router_manager.delete_rule(client)

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to delete rule for {client}")

        return {
            "status": "success",
            "message": f"Rule deleted for {client} (set to unlimited bandwidth)"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients")
async def list_clients():
    """List all running device containers from database"""
    running_devices = db_service.get_running_devices()

    clients = []
    for device in running_devices:
        clients.append({
            "name": device.name,
            "ip": device.ip_address,
            "interface": device.interface_name,
            "cluster_id": device.cluster_id,
            "status": device.status
        })

    return {"clients": clients}


@router.post("/traffic/start")
async def start_traffic(request: TrafficControlRequest) -> Dict[str, str]:
    """
    Start iperf3 traffic from a client to the router

    The client will send traffic for the specified duration
    """
    # Find device by name in database
    all_devices = db_service.get_running_devices()
    device = None
    for d in all_devices:
        if d.name == request.client:
            device = d
            break

    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{request.client}' not found or not running")

    if not device.router_ip:
        raise HTTPException(status_code=400, detail=f"Device '{request.client}' has no router IP configured")

    # Use device's router IP and a dynamic port based on interface
    router_ip = device.router_ip
    # Extract interface number (eth5 -> 5) for port assignment
    interface_num = device.interface_name.replace('eth', '') if device.interface_name else '1'
    port = 5200 + int(interface_num)  # eth5 -> port 5205, eth6 -> port 5206, etc.

    # Stop any existing iperf3 process
    docker_executor.exec_command(device.container_name, "sh -c 'pkill iperf3 || true'")

    # Build iperf3 command with optional bandwidth limit
    # Use -R (reverse mode) so router sends to client, allowing us to measure downstream bandwidth
    bandwidth_flag = f" -b {request.bandwidth}" if request.bandwidth else ""
    cmd = f"nohup iperf3 -c {router_ip} -p {port} -t {request.duration} -R{bandwidth_flag} > /dev/null 2>&1 &"
    exit_code, output = docker_executor.exec_command(device.container_name, f"sh -c '{cmd}'")

    if exit_code != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start traffic on {request.client}: {output}"
        )

    return {
        "status": "success",
        "message": f"Traffic started from {request.client} to router for {request.duration}s",
        "client": request.client,
        "router_ip": router_ip
    }


@router.post("/traffic/stop")
async def stop_traffic(request: TrafficControlRequest) -> Dict[str, str]:
    """
    Stop iperf3 traffic on a client
    """
    # Find device by name in database
    all_devices = db_service.get_running_devices()
    device = None
    for d in all_devices:
        if d.name == request.client:
            device = d
            break

    if not device:
        raise HTTPException(status_code=404, detail=f"Device '{request.client}' not found or not running")

    # Stop iperf3 process
    exit_code, output = docker_executor.exec_command(device.container_name, "sh -c 'pkill iperf3 || true'")

    return {
        "status": "success",
        "message": f"Traffic stopped on {request.client}",
        "client": request.client
    }


@router.get("/traffic/status")
async def get_traffic_status() -> Dict[str, List[Dict]]:
    """
    Get status of iperf3 processes on all running devices
    """
    # Get all running devices from database
    running_devices = db_service.get_running_devices()
    status_list = []

    for device in running_devices:
        try:
            # Check if iperf3 is running using container name
            exit_code, output = docker_executor.exec_command(device.container_name, "pgrep iperf3")
            is_running = exit_code == 0 and output.strip() != ""

            status_list.append({
                "client": device.name,
                "active": is_running,
                "pid": output.strip() if is_running else None
            })
        except Exception as e:
            # Container might not exist or be accessible
            status_list.append({
                "client": device.name,
                "active": False,
                "pid": None,
                "error": str(e)
            })

    return {"traffic_status": status_list}


# ========== NEW ENDPOINTS: Dynamic Cluster & Device Management ==========

# Request/Response Models
class ClusterCreate(BaseModel):
    """Request model for creating a cluster"""
    name: str
    description: str = ""
    active: bool = False


class ClusterUpdate(BaseModel):
    """Request model for updating a cluster"""
    name: Optional[str] = None
    description: Optional[str] = None


class DeviceCreate(BaseModel):
    """Request model for creating a device"""
    cluster_id: int
    name: str
    device_type: str = "pc"


# ========== CLUSTER ENDPOINTS ==========

@router.post("/clusters")
async def create_cluster(cluster: ClusterCreate) -> Dict:
    """Create a new cluster"""
    try:
        new_cluster = db_service.create_cluster(
            name=cluster.name,
            description=cluster.description,
            active=cluster.active
        )
        return {
            "id": new_cluster.id,
            "name": new_cluster.name,
            "description": new_cluster.description,
            "active": new_cluster.active,
            "created_at": new_cluster.created_at.isoformat() if new_cluster.created_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create cluster: {str(e)}")


@router.get("/clusters")
async def list_clusters(active_only: bool = False) -> List[Dict]:
    """List all clusters"""
    try:
        clusters = db_service.list_clusters(active_only=active_only)
        return [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "active": c.active,
                "device_count": len(c.devices),
                "created_at": c.created_at.isoformat() if c.created_at else None
            }
            for c in clusters
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list clusters: {str(e)}")


@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: int) -> Dict:
    """Get cluster details with devices"""
    try:
        cluster = db_service.get_cluster(cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")

        return {
            "id": cluster.id,
            "name": cluster.name,
            "description": cluster.description,
            "active": cluster.active,
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "device_type": d.device_type,
                    "ip_address": d.ip_address,
                    "status": d.status,
                    "interface_name": d.interface_name,
                    "container_name": d.container_name
                }
                for d in cluster.devices
            ],
            "created_at": cluster.created_at.isoformat() if cluster.created_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cluster: {str(e)}")


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: int, update: ClusterUpdate) -> Dict:
    """Update cluster properties"""
    try:
        success = db_service.update_cluster(
            cluster_id=cluster_id,
            name=update.name,
            description=update.description
        )
        if not success:
            raise HTTPException(status_code=404, detail="Cluster not found")
        return {"status": "success", "cluster_id": cluster_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update cluster: {str(e)}")


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: int) -> Dict:
    """Delete cluster, destroy all its containers, and clean up networks"""
    try:
        # Get cluster and its devices before deletion
        cluster = db_service.get_cluster(cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")

        devices = db_service.get_cluster_devices(cluster_id)

        # Destroy all containers for devices in this cluster
        destroyed_count = 0
        errors = []
        for device in devices:
            try:
                success, error = container_manager.destroy_device_container(device)
                if success:
                    destroyed_count += 1
                else:
                    errors.append(f"{device.name}: {error}")
            except Exception as e:
                errors.append(f"{device.name}: {str(e)}")

        # Now delete the cluster from database (cascades to devices)
        success = db_service.delete_cluster(cluster_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete cluster from database")

        return {
            "status": "success",
            "cluster_id": cluster_id,
            "containers_destroyed": destroyed_count,
            "errors": errors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete cluster: {str(e)}")


@router.post("/clusters/{cluster_id}/activate")
async def activate_cluster(cluster_id: int) -> Dict:
    """Activate a cluster (multi-cluster: doesn't deactivate others)"""
    try:
        success = db_service.activate_cluster(cluster_id)
        if not success:
            raise HTTPException(status_code=404, detail="Cluster not found")
        return {"status": "success", "cluster_id": cluster_id, "active": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to activate cluster: {str(e)}")


@router.post("/clusters/{cluster_id}/deactivate")
async def deactivate_cluster(cluster_id: int) -> Dict:
    """Deactivate a cluster"""
    try:
        success = db_service.deactivate_cluster(cluster_id)
        if not success:
            raise HTTPException(status_code=404, detail="Cluster not found")
        return {"status": "success", "cluster_id": cluster_id, "active": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate cluster: {str(e)}")


# ========== DEVICE ENDPOINTS ==========

@router.post("/devices")
async def create_device(device: DeviceCreate) -> Dict:
    """Create a device in a cluster"""
    try:
        cluster = db_service.get_cluster(device.cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")

        # Calculate network config based on existing device count
        octet, subnet = db_service.get_next_available_network(device.cluster_id)

        # Sanitize names for Docker (no spaces allowed)
        safe_cluster_name = sanitize_container_name(cluster.name)
        safe_device_name = sanitize_container_name(device.name)

        network_config = {
            "subnet": subnet,
            "network_name": f"qc_net_{safe_cluster_name}_{safe_device_name}",
            "container_name": f"qc_{safe_cluster_name}_{safe_device_name}",
            "device_ip": f"10.{octet}.0.10",
            "router_ip": f"10.{octet}.0.254",
        }

        new_device = db_service.create_device(
            cluster_id=device.cluster_id,
            name=device.name,
            device_type=device.device_type,
            network_config=network_config
        )

        return {
            "id": new_device.id,
            "name": new_device.name,
            "device_type": new_device.device_type,
            "cluster_id": new_device.cluster_id,
            "ip_address": new_device.ip_address,
            "container_name": new_device.container_name,
            "status": new_device.status
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create device: {str(e)}")


@router.get("/devices")
async def list_devices(cluster_id: Optional[int] = None) -> List[Dict]:
    """List devices, optionally filtered by cluster"""
    try:
        if cluster_id:
            devices = db_service.get_cluster_devices(cluster_id)
        else:
            devices = db_service.get_all_active_cluster_devices()

        return [
            {
                "id": d.id,
                "cluster_id": d.cluster_id,
                "name": d.name,
                "device_type": d.device_type,
                "ip_address": d.ip_address,
                "container_name": d.container_name,
                "status": d.status,
                "interface_name": d.interface_name,
                "error_message": d.error_message
            }
            for d in devices
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list devices: {str(e)}")


@router.get("/devices/{device_id}")
async def get_device(device_id: int) -> Dict:
    """Get device details"""
    try:
        device = db_service.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        return {
            "id": device.id,
            "cluster_id": device.cluster_id,
            "name": device.name,
            "device_type": device.device_type,
            "ip_address": device.ip_address,
            "router_ip": device.router_ip,
            "container_name": device.container_name,
            "network_name": device.network_name,
            "status": device.status,
            "interface_name": device.interface_name,
            "ifb_device": device.ifb_device,
            "error_message": device.error_message
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get device: {str(e)}")


@router.delete("/devices/{device_id}")
async def delete_device(device_id: int) -> Dict:
    """Delete a device and destroy its container"""
    try:
        # Get device before deletion
        device = db_service.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        # Destroy container if it exists
        container_destroyed = False
        error_message = None
        try:
            success, error = container_manager.destroy_device_container(device)
            if success:
                container_destroyed = True
            else:
                error_message = error
        except Exception as e:
            error_message = str(e)

        # Delete from database
        success = db_service.delete_device(device_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete device from database")

        return {
            "status": "success",
            "device_id": device_id,
            "container_destroyed": container_destroyed,
            "error": error_message
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete device: {str(e)}")


# ========== SYNC ENDPOINTS ==========

@router.get("/sync/preview")
async def preview_sync(cluster_id: Optional[int] = None) -> Dict:
    """Preview what sync would do without executing"""
    try:
        preview = sync_service.get_sync_preview(cluster_id=cluster_id)
        return preview.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to preview sync: {str(e)}")


@router.post("/sync")
async def sync_devices(cluster_id: Optional[int] = None) -> Dict:
    """
    Reconcile desired state (DB) with actual state (Docker).

    If cluster_id not provided, syncs all active clusters.
    """
    try:
        if cluster_id:
            result = sync_service.sync_cluster(cluster_id)
        else:
            result = sync_service.sync_active_clusters()

        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync: {str(e)}")


# ========== CONTAINER MANAGEMENT ENDPOINTS ==========

@router.get("/containers/status")
async def get_container_status() -> Dict:
    """Get status of all containers"""
    try:
        running = container_manager.get_running_containers()

        # Also get infrastructure containers (frontend, backend, router)
        infrastructure_containers = []
        for container_name in ["frontend", "backend", "router"]:
            try:
                container = container_manager.client.containers.get(container_name)
                infrastructure_containers.append({
                    "name": container.name,
                    "status": container.status,
                    "id": container.id[:12],
                    "created": container.attrs['Created']
                })
            except:
                # Container doesn't exist or isn't running
                pass

        # Combine client and infrastructure containers
        all_containers = running + infrastructure_containers

        # Get all devices from active clusters
        active_devices = db_service.get_all_active_cluster_devices()

        return {
            "running_containers": all_containers,
            "devices": [
                {
                    "id": d.id,
                    "name": d.name,
                    "container_name": d.container_name,
                    "status": d.status,
                    "interface_name": d.interface_name,
                    "error_message": d.error_message
                }
                for d in active_devices
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get container status: {str(e)}")


@router.post("/containers/kill-all")
async def kill_all_containers() -> Dict:
    """Stop and remove all client containers (emergency shutdown)"""
    try:
        count, errors = container_manager.kill_all_client_containers()

        # Update all device statuses to stopped
        all_devices = db_service.get_all_active_cluster_devices()
        for device in all_devices:
            try:
                db_service.update_device_status(
                    device.id,
                    "stopped",
                    interface_name=None,
                    ifb_device=None
                )
            except:
                pass

        return {
            "status": "success",
            "containers_killed": count,
            "errors": errors
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to kill containers: {str(e)}")
