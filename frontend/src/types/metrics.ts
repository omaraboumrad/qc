export interface InterfaceClassStats {
  classid: string;
  bytes: number;
  packets: number;
  drops: number;
  overlimits: number;
  rate?: string;
  ceil?: string;
}

export interface DirectionalStats {
  bandwidth_mbps: number;
  packets_sent: number;
  packets_dropped: number;
  utilization_percent: number;
  classes: Record<string, InterfaceClassStats>;
}

export interface InterfaceStats {
  name: string;
  client: string;

  // New bidirectional fields
  downstream?: DirectionalStats;  // Router → client
  upstream?: DirectionalStats;    // Client → router

  // Legacy fields for backward compatibility
  bandwidth_mbps?: number;
  packets_sent?: number;
  packets_dropped?: number;
  utilization_percent?: number;
  classes?: Record<string, InterfaceClassStats>;
}

export interface Connection {
  client: string;
  protocol: string;
  local_addr: string;
  remote_addr: string;
  state: string;
}

export interface TrafficRule {
  interface: string;
  client: string;
  class_id: string;

  // New bidirectional fields
  downstream_rate?: string;
  downstream_ceil?: string;
  upstream_rate?: string;
  upstream_ceil?: string;

  // Legacy fields for backward compatibility
  rate?: string;
  ceil?: string;

  active: boolean;
}

export interface MetricsSnapshot {
  timestamp: number;
  interfaces: Record<string, InterfaceStats>;
  connections: Connection[];
  rules: TrafficRule[];
}

export interface BandwidthRule {
  interface: string;
  client: string;
  class_id?: string;

  // New bidirectional fields
  downstream_rate?: string;
  downstream_ceil?: string;
  upstream_rate?: string;
  upstream_ceil?: string;

  // Legacy fields for backward compatibility
  rate?: string;
  ceil?: string;

  description?: string;
}
