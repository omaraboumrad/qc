from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
from pydantic import BaseModel
from ..services.metrics_collector import MetricsCollector
from ..services.router_manager import RouterManager
from ..utils.docker_exec import DockerExecutor
from ..models.metrics import MetricsSnapshot
from ..models.rules import BandwidthRule, RuleConfig

router = APIRouter()

# Service instances
metrics_collector = MetricsCollector()
router_manager = RouterManager()
docker_executor = DockerExecutor()


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
