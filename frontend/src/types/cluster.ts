export interface Cluster {
  id: number;
  name: string;
  description: string;
  active: boolean;
  device_count?: number;
  devices?: Device[];
  created_at: string;
}

export interface Device {
  id: number;
  cluster_id: number;
  name: string;
  device_type: string;
  ip_address: string;
  container_name: string;
  status: 'stopped' | 'starting' | 'running' | 'stopping' | 'error';
  interface_name: string | null;
  error_message: string | null;
}

export interface ClusterCreate {
  name: string;
  description?: string;
  active?: boolean;
}

export interface ClusterUpdate {
  name?: string;
  description?: string;
  active?: boolean;
}

export interface DeviceCreate {
  cluster_id: number;
  name: string;
  device_type: string;
}

export interface SyncPreview {
  to_create: string[];
  to_destroy: string[];
  to_keep: string[];
  total_changes: number;
}

export interface SyncResult {
  created: string[];
  destroyed: string[];
  kept: string[];
  updated: string[];
  errors: string[];
  total_operations: number;
  success_count: number;
  error_count: number;
}

export interface ContainerStatus {
  running_containers: {
    name: string;
    status: string;
    id: string;
    created: string;
  }[];
  devices: Device[];
}
