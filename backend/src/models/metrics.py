from pydantic import BaseModel
from typing import Dict, List, Optional


class InterfaceClassStats(BaseModel):
    """Statistics for a single traffic class"""
    classid: str
    bytes: int
    packets: int
    drops: int
    overlimits: int
    rate: Optional[str] = None
    ceil: Optional[str] = None


class DirectionalStats(BaseModel):
    """Statistics for one direction (upstream or downstream)"""
    bandwidth_mbps: float
    packets_sent: int
    packets_dropped: int
    utilization_percent: float
    classes: Dict[str, InterfaceClassStats]


class InterfaceStats(BaseModel):
    """Statistics for a single network interface with bidirectional support"""
    name: str
    client: str

    # New bidirectional fields
    downstream: Optional['DirectionalStats'] = None  # Router → client (physical egress)
    upstream: Optional['DirectionalStats'] = None    # Client → router (IFB egress)

    # Legacy fields for backward compatibility
    bandwidth_mbps: Optional[float] = None
    packets_sent: Optional[int] = None
    packets_dropped: Optional[int] = None
    utilization_percent: Optional[float] = None
    classes: Optional[Dict[str, InterfaceClassStats]] = None


class Connection(BaseModel):
    """Active iperf3 connection"""
    client: str
    protocol: str
    local_addr: str
    remote_addr: str
    state: str


class TrafficRule(BaseModel):
    """Active traffic shaping rule with bidirectional support"""
    interface: str
    client: str
    class_id: str

    # New bidirectional fields
    downstream_rate: Optional[str] = None
    downstream_ceil: Optional[str] = None
    upstream_rate: Optional[str] = None
    upstream_ceil: Optional[str] = None

    # Legacy fields for backward compatibility
    rate: Optional[str] = None
    ceil: Optional[str] = None

    active: bool


class MetricsSnapshot(BaseModel):
    """Complete metrics snapshot"""
    timestamp: float
    interfaces: Dict[str, InterfaceStats]
    connections: List[Connection]
    rules: List[TrafficRule]
