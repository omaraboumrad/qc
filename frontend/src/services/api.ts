import axios from 'axios';
import { MetricsSnapshot, BandwidthRule } from '../types/metrics';
import {
  Cluster,
  Device,
  ClusterCreate,
  ClusterUpdate,
  DeviceCreate,
  SyncPreview,
  SyncResult,
  ContainerStatus,
} from '../types/cluster';

const API_BASE_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const apiService = {
  // Get current metrics snapshot
  getCurrentMetrics: async (): Promise<MetricsSnapshot> => {
    const response = await api.get<MetricsSnapshot>('/metrics/current');
    return response.data;
  },

  // Get current rules
  getRules: async () => {
    const response = await api.get('/rules');
    return response.data;
  },

  // Apply a single bandwidth rule
  applySingleRule: async (rule: BandwidthRule) => {
    const response = await api.post('/rules/apply-single', rule);
    return response.data;
  },

  // Reset rules to defaults
  resetRules: async () => {
    const response = await api.post('/rules/reset');
    return response.data;
  },

  // Delete a rule (set to unlimited bandwidth)
  deleteRule: async (client: string) => {
    const response = await api.delete(`/rules/${client}`);
    return response.data;
  },

  // Get list of clients
  getClients: async () => {
    const response = await api.get('/clients');
    return response.data;
  },

  // Traffic control methods
  startTraffic: async (client: string, duration: number = 300) => {
    const response = await api.post('/traffic/start', { client, duration });
    return response.data;
  },

  stopTraffic: async (client: string) => {
    const response = await api.post('/traffic/stop', { client });
    return response.data;
  },

  getTrafficStatus: async () => {
    const response = await api.get('/traffic/status');
    return response.data;
  },

  // Cluster Management
  getClusters: async (): Promise<Cluster[]> => {
    const response = await api.get<Cluster[]>('/clusters');
    return response.data;
  },

  getCluster: async (clusterId: number): Promise<Cluster> => {
    const response = await api.get<Cluster>(`/clusters/${clusterId}`);
    return response.data;
  },

  createCluster: async (cluster: ClusterCreate): Promise<Cluster> => {
    const response = await api.post<Cluster>('/clusters', cluster);
    return response.data;
  },

  updateCluster: async (clusterId: number, cluster: ClusterUpdate): Promise<{ status: string }> => {
    const response = await api.put(`/clusters/${clusterId}`, cluster);
    return response.data;
  },

  deleteCluster: async (clusterId: number): Promise<{ status: string }> => {
    const response = await api.delete(`/clusters/${clusterId}`);
    return response.data;
  },

  activateCluster: async (clusterId: number): Promise<{ status: string }> => {
    const response = await api.post(`/clusters/${clusterId}/activate`);
    return response.data;
  },

  deactivateCluster: async (clusterId: number): Promise<{ status: string }> => {
    const response = await api.post(`/clusters/${clusterId}/deactivate`);
    return response.data;
  },

  // Device Management
  getDevices: async (clusterId?: number): Promise<Device[]> => {
    const url = clusterId ? `/devices?cluster_id=${clusterId}` : '/devices';
    const response = await api.get<Device[]>(url);
    return response.data;
  },

  getDevice: async (deviceId: number): Promise<Device> => {
    const response = await api.get<Device>(`/devices/${deviceId}`);
    return response.data;
  },

  createDevice: async (device: DeviceCreate): Promise<Device> => {
    const response = await api.post<Device>('/devices', device);
    return response.data;
  },

  deleteDevice: async (deviceId: number): Promise<{ status: string }> => {
    const response = await api.delete(`/devices/${deviceId}`);
    return response.data;
  },

  // Sync Operations
  getSyncPreview: async (clusterId?: number): Promise<SyncPreview> => {
    const url = clusterId ? `/sync/preview?cluster_id=${clusterId}` : '/sync/preview';
    const response = await api.get<SyncPreview>(url);
    return response.data;
  },

  executeSync: async (clusterId?: number): Promise<SyncResult> => {
    const url = clusterId ? `/sync?cluster_id=${clusterId}` : '/sync';
    const response = await api.post<SyncResult>(url);
    return response.data;
  },

  // Container Management
  getContainerStatus: async (): Promise<ContainerStatus> => {
    const response = await api.get<ContainerStatus>('/containers/status');
    return response.data;
  },

  killAllContainers: async (): Promise<{ status: string; containers_killed: number; errors: string[] }> => {
    const response = await api.post('/containers/kill-all');
    return response.data;
  },
};

export const SSE_STREAM_URL = `${API_BASE_URL}/api/metrics/stream`;
