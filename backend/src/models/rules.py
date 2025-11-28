from pydantic import BaseModel, Field
from typing import Optional


class BandwidthRule(BaseModel):
    """Bandwidth limiting rule with bidirectional support"""
    interface: str = Field(..., description="Network interface (eth1-eth4)")
    client: str = Field(..., description="Client name (pc1, pc2, mb1, mb2)")
    class_id: str = Field(default="1:30", description="Traffic class ID")

    # Bidirectional rates (new fields)
    downstream_rate: Optional[str] = Field(None, description="Downstream guaranteed rate - router to client (e.g., '20mbit')")
    downstream_ceil: Optional[str] = Field(None, description="Downstream maximum rate ceiling (e.g., '50mbit')")
    upstream_rate: Optional[str] = Field(None, description="Upstream guaranteed rate - client to router (e.g., '10mbit')")
    upstream_ceil: Optional[str] = Field(None, description="Upstream maximum rate ceiling (e.g., '30mbit')")

    # Legacy fields for backward compatibility
    rate: Optional[str] = Field(None, description="Legacy: Guaranteed rate (e.g., '20mbit')")
    ceil: Optional[str] = Field(None, description="Legacy: Maximum rate ceiling (e.g., '50mbit')")

    description: Optional[str] = None


class QoSRule(BaseModel):
    """QoS priority rule"""
    name: str
    protocol: str = Field(..., description="Protocol (tcp, udp, icmp)")
    port: Optional[int] = Field(None, description="Port number")
    tos: str = Field(..., description="Type of Service value (e.g., '0x10')")
    class_id: str = Field(..., description="Target traffic class")
    enabled: bool = True
    description: Optional[str] = None


class RuleConfig(BaseModel):
    """Complete traffic shaping configuration"""
    rules: list[BandwidthRule]
    qos_rules: Optional[list[QoSRule]] = []
