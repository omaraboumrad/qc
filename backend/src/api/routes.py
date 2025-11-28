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
    valid_clients = ["pc1", "pc2", "mb1", "mb2"]

    if client not in valid_clients:
        raise HTTPException(status_code=400, detail=f"Invalid client: {client}")

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
    """List all client containers"""
    return {
        "clients": [
            {"name": "pc1", "ip": "10.1.0.10", "interface": "eth1"},
            {"name": "pc2", "ip": "10.2.0.10", "interface": "eth2"},
            {"name": "mb1", "ip": "10.3.0.10", "interface": "eth3"},
            {"name": "mb2", "ip": "10.4.0.10", "interface": "eth4"},
        ]
    }


@router.post("/traffic/start")
async def start_traffic(request: TrafficControlRequest) -> Dict[str, str]:
    """
    Start iperf3 traffic from a client to the router

    The client will send traffic for the specified duration
    """
    client_config = {
        "pc1": {"ip": "10.1.0.254", "port": 5201},
        "pc2": {"ip": "10.2.0.254", "port": 5202},
        "mb1": {"ip": "10.3.0.254", "port": 5203},
        "mb2": {"ip": "10.4.0.254", "port": 5204},
    }

    if request.client not in client_config:
        raise HTTPException(status_code=400, detail=f"Invalid client: {request.client}")

    config = client_config[request.client]
    router_ip = config["ip"]
    port = config["port"]

    # Stop any existing iperf3 process
    docker_executor.exec_client(request.client, "sh -c 'pkill iperf3 || true'")

    # Build iperf3 command with optional bandwidth limit
    # Use -R (reverse mode) so router sends to client, allowing us to measure downstream bandwidth
    bandwidth_flag = f" -b {request.bandwidth}" if request.bandwidth else ""
    cmd = f"nohup iperf3 -c {router_ip} -p {port} -t {request.duration} -R{bandwidth_flag} > /dev/null 2>&1 &"
    exit_code, output = docker_executor.exec_client(request.client, f"sh -c '{cmd}'")

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
    valid_clients = ["pc1", "pc2", "mb1", "mb2"]

    if request.client not in valid_clients:
        raise HTTPException(status_code=400, detail=f"Invalid client: {request.client}")

    # Stop iperf3 process
    exit_code, output = docker_executor.exec_client(request.client, "sh -c 'pkill iperf3 || true'")

    return {
        "status": "success",
        "message": f"Traffic stopped on {request.client}",
        "client": request.client
    }


@router.get("/traffic/status")
async def get_traffic_status() -> Dict[str, List[Dict]]:
    """
    Get status of iperf3 processes on all clients
    """
    clients = ["pc1", "pc2", "mb1", "mb2"]
    status_list = []

    for client in clients:
        # Check if iperf3 is running
        exit_code, output = docker_executor.exec_client(client, "pgrep iperf3")
        is_running = exit_code == 0 and output.strip() != ""

        status_list.append({
            "client": client,
            "active": is_running,
            "pid": output.strip() if is_running else None
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
    """Delete cluster and all its devices"""
    try:
        success = db_service.delete_cluster(cluster_id)
        if not success:
            raise HTTPException(status_code=404, detail="Cluster not found")
        return {"status": "success", "cluster_id": cluster_id}
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

        network_config = {
            "subnet": subnet,
            "network_name": f"qc_net_{cluster.name}_{device.name}",
            "container_name": f"qc_{cluster.name}_{device.name}",
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
    """Delete a device"""
    try:
        success = db_service.delete_device(device_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"status": "success", "device_id": device_id}
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

        # Get all devices from active clusters
        active_devices = db_service.get_all_active_cluster_devices()

        return {
            "running_containers": running,
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
