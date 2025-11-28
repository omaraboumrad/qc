import axios from 'axios';
import { MetricsSnapshot, BandwidthRule } from '../types/metrics';

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
};

export const SSE_STREAM_URL = `${API_BASE_URL}/api/metrics/stream`;
