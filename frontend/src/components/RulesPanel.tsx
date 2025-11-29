import { useState, useEffect } from 'react';
import { TrafficRule, BandwidthRule } from '../types/metrics';
import { apiService } from '../services/api';
import { Cluster, Device, SyncPreview, ContainerStatus } from '../types/cluster';

interface Props {
  rules: TrafficRule[];
}

interface ClientState {
  upRate: string;
  upCeil: string;
  downRate: string;
  downCeil: string;
  trafficAmount: string;
  trafficRunning: boolean;
}

// Editing states
interface ClusterEditState {
  id: number | null; // null for new cluster
  name: string;
  description: string;
  isNew: boolean;
}

interface DeviceEditState {
  id: number | null; // null for new device
  clusterId: number;
  name: string;
  deviceType: string;
  isNew: boolean;
}

export default function RulesPanel({ rules }: Props) {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [syncPreviews, setSyncPreviews] = useState<Map<number, SyncPreview>>(new Map());
  const [clientStates, setClientStates] = useState<Record<string, ClientState>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showModal, setShowModal] = useState(false);

  // Editing states
  const [editingCluster, setEditingCluster] = useState<ClusterEditState | null>(null);
  const [editingDevice, setEditingDevice] = useState<DeviceEditState | null>(null);

  // Container status
  const [containerStatus, setContainerStatus] = useState<ContainerStatus | null>(null);

  // Load clusters and devices
  useEffect(() => {
    const loadData = async () => {
      try {
        const clustersData = await apiService.getClusters();
        setClusters(clustersData);

        // Load devices for all clusters
        const allDevices: Device[] = [];
        for (const cluster of clustersData) {
          const clusterDevices = await apiService.getDevices(cluster.id);
          allDevices.push(...clusterDevices);
        }
        setDevices(allDevices);

        // Load sync previews for all clusters
        const previews = new Map<number, SyncPreview>();
        for (const cluster of clustersData) {
          try {
            const preview = await apiService.getSyncPreview(cluster.id);
            if (preview.total_changes > 0) {
              previews.set(cluster.id, preview);
            }
          } catch (err) {
            console.error(`Failed to load sync preview for cluster ${cluster.id}:`, err);
          }
        }
        setSyncPreviews(previews);
      } catch (err) {
        console.error('Failed to load clusters/devices:', err);
      }
    };

    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  // Initialize state from current rules
  useEffect(() => {
    setClientStates(prev => {
      const newStates: Record<string, ClientState> = {};

      devices.forEach(device => {
        const rule = rules.find(r => r.client === device.name);
        const existingState = prev[device.name];

        const cleanBandwidth = (value?: string) => {
          if (!value) return '';
          const normalized = value.replace('Mbit', 'mbit');
          if (normalized === '1gbit' || normalized === '1Gbit') return '';
          return normalized;
        };

        newStates[device.name] = {
          upRate: existingState?.upRate !== undefined ? existingState.upRate : cleanBandwidth(rule?.upstream_rate),
          upCeil: existingState?.upCeil !== undefined ? existingState.upCeil : cleanBandwidth(rule?.upstream_ceil),
          downRate: existingState?.downRate !== undefined ? existingState.downRate : cleanBandwidth(rule?.downstream_rate || rule?.rate),
          downCeil: existingState?.downCeil !== undefined ? existingState.downCeil : cleanBandwidth(rule?.downstream_ceil || rule?.ceil),
          trafficAmount: existingState?.trafficAmount || '50M',
          trafficRunning: existingState?.trafficRunning || false,
        };
      });
      return newStates;
    });
  }, [rules, devices]);

  // Poll traffic status every 2 seconds
  useEffect(() => {
    const checkTrafficStatus = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/traffic/status');
        const data = await response.json();

        setClientStates(prev => {
          const updated = { ...prev };
          data.traffic_status.forEach((status: any) => {
            if (updated[status.client]) {
              updated[status.client] = {
                ...updated[status.client],
                trafficRunning: status.active
              };
            }
          });
          return updated;
        });
      } catch (error) {
        // Silently fail
      }
    };

    checkTrafficStatus();
    const interval = setInterval(checkTrafficStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Poll container status every 3 seconds
  useEffect(() => {
    const checkContainerStatus = async () => {
      try {
        const status = await apiService.getContainerStatus();
        setContainerStatus(status);
      } catch (error) {
        // Silently fail
      }
    };

    checkContainerStatus();
    const interval = setInterval(checkContainerStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const reloadData = async () => {
    try {
      const clustersData = await apiService.getClusters();
      setClusters(clustersData);

      const allDevices: Device[] = [];
      for (const cluster of clustersData) {
        const clusterDevices = await apiService.getDevices(cluster.id);
        allDevices.push(...clusterDevices);
      }
      setDevices(allDevices);

      const previews = new Map<number, SyncPreview>();
      for (const cluster of clustersData) {
        try {
          const preview = await apiService.getSyncPreview(cluster.id);
          if (preview.total_changes > 0) {
            previews.set(cluster.id, preview);
          }
        } catch (err) {
          console.error(`Failed to load sync preview for cluster ${cluster.id}:`, err);
        }
      }
      setSyncPreviews(previews);
    } catch (err) {
      console.error('Failed to reload data:', err);
    }
  };

  const updateClientState = (clientName: string, field: keyof ClientState, value: string | boolean) => {
    setClientStates(prev => ({
      ...prev,
      [clientName]: {
        ...prev[clientName],
        [field]: value
      }
    }));
  };

  const handleApply = async (device: Device) => {
    setLoading(device.name);
    setMessage(null);

    try {
      if (!device.interface_name) {
        throw new Error('Device has no interface assigned');
      }

      const state = clientStates[device.name];

      const rule: BandwidthRule = {
        interface: device.interface_name,
        client: device.name,
        class_id: '1:30',
        downstream_rate: state.downRate || '1gbit',
        downstream_ceil: state.downCeil || '1gbit',
        upstream_rate: state.upRate || '1gbit',
        upstream_ceil: state.upCeil || '1gbit',
        description: `Bidirectional rule for ${device.name}`,
      };

      await apiService.applySingleRule(rule);
      setMessage({
        type: 'success',
        text: `Rule applied to ${device.name}`
      });
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleReset = async (deviceName: string) => {
    setLoading(deviceName);
    setMessage(null);

    try {
      await apiService.deleteRule(deviceName);
      setMessage({ type: 'success', text: `${deviceName} reset to unlimited` });
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleToggleTraffic = async (deviceName: string) => {
    setLoading(deviceName);
    setMessage(null);

    try {
      const state = clientStates[deviceName];

      if (state.trafficRunning) {
        const response = await fetch(`http://localhost:8000/api/traffic/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client: deviceName })
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to stop traffic');
        }

        setMessage({ type: 'success', text: `Stopped traffic for ${deviceName}` });
      } else {
        const response = await fetch(`http://localhost:8000/api/traffic/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client: deviceName,
            duration: 300,
            bandwidth: state.trafficAmount
          })
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to start traffic');
        }

        setMessage({ type: 'success', text: `Started traffic for ${deviceName} at ${state.trafficAmount}` });
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || 'Failed to toggle traffic' });
    } finally {
      setLoading(null);
    }
  };

  const handleAddCluster = () => {
    setEditingCluster({
      id: null,
      name: '',
      description: '',
      isNew: true
    });
  };

  const handleSaveCluster = async () => {
    if (!editingCluster) return;

    setLoading('cluster-edit');
    setMessage(null);

    try {
      if (editingCluster.isNew) {
        const newCluster = await apiService.createCluster({
          name: editingCluster.name,
          description: editingCluster.description,
          active: true
        });
        setMessage({ type: 'success', text: `Cluster "${newCluster.name}" created` });
      } else if (editingCluster.id !== null) {
        await apiService.updateCluster(editingCluster.id, {
          name: editingCluster.name,
          description: editingCluster.description
        });
        setMessage({ type: 'success', text: `Cluster updated` });
      }

      setEditingCluster(null);
      await reloadData();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleCancelClusterEdit = () => {
    setEditingCluster(null);
  };

  const handleAddDevice = (clusterId: number) => {
    setEditingDevice({
      id: null,
      clusterId,
      name: '',
      deviceType: 'pc',
      isNew: true
    });
  };

  const handleSaveDevice = async () => {
    if (!editingDevice) return;

    setLoading('device-edit');
    setMessage(null);

    try {
      const newDevice = await apiService.createDevice({
        cluster_id: editingDevice.clusterId,
        name: editingDevice.name,
        device_type: editingDevice.deviceType
      });
      setMessage({ type: 'success', text: `Device "${newDevice.name}" created` });
      setEditingDevice(null);
      await reloadData();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleCancelDeviceEdit = () => {
    setEditingDevice(null);
  };

  const handleDeleteCluster = async (cluster: Cluster) => {
    if (!confirm(`Delete cluster "${cluster.name}" and all its devices?`)) {
      return;
    }

    setLoading(`cluster-${cluster.id}`);
    setMessage(null);

    try {
      await apiService.deleteCluster(cluster.id);
      setMessage({ type: 'success', text: `Cluster "${cluster.name}" deleted` });
      await reloadData();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleDeleteDevice = async (device: Device) => {
    if (!confirm(`Delete device "${device.name}"?`)) {
      return;
    }

    setLoading(`device-${device.id}`);
    setMessage(null);

    try {
      await apiService.deleteDevice(device.id);
      setMessage({ type: 'success', text: `Device "${device.name}" deleted` });
      await reloadData();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleSyncCluster = async (clusterId: number) => {
    if (!confirm('Execute sync? This will create/destroy containers to match the desired state.')) {
      return;
    }

    setLoading(`sync-${clusterId}`);
    setMessage(null);

    try {
      const result = await apiService.executeSync(clusterId);
      const summary = [
        result.created.length > 0 ? `Created: ${result.created.length}` : null,
        result.destroyed.length > 0 ? `Destroyed: ${result.destroyed.length}` : null,
        result.errors.length > 0 ? `Errors: ${result.errors.length}` : null,
      ].filter(Boolean).join(', ');

      setMessage({ type: 'success', text: `Sync complete! ${summary || 'No changes'}` });
      await reloadData();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleKillAllContainers = async () => {
    if (!confirm('Kill ALL client containers?\n\nThis will:\n1. Stop and remove ALL QC client containers\n2. Update all device statuses to "stopped"\n3. Leave networks intact (they will be reused on next sync)\n\nAre you sure?')) {
      return;
    }

    setLoading('kill-all');
    setMessage(null);

    try {
      const result = await apiService.killAllContainers();
      setMessage({ type: 'success', text: `Killed ${result.containers_killed} containers successfully!` });
      await reloadData();
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const generateTcCommands = () => {
    const commands: string[] = [];

    rules.forEach(rule => {
      const device = devices.find(d => d.name === rule.client);

      const downRate = rule.downstream_rate || rule.rate || '1gbit';
      const downCeil = rule.downstream_ceil || rule.ceil || '1gbit';
      commands.push(
        `# ${rule.client} - Downstream (${rule.interface})`,
        `tc class change dev ${rule.interface} parent 1:1 classid 1:30 htb rate ${downRate} ceil ${downCeil}`
      );

      if (device?.ifb_device && (rule.upstream_rate || rule.upstream_ceil)) {
        const upRate = rule.upstream_rate || '1gbit';
        const upCeil = rule.upstream_ceil || '1gbit';
        commands.push(
          `# ${rule.client} - Upstream (${device.ifb_device})`,
          `tc class change dev ${device.ifb_device} parent 2:1 classid 2:30 htb rate ${upRate} ceil ${upCeil}`
        );
      }

      commands.push('');
    });

    return commands.join('\n');
  };

  const handleCopyRules = () => {
    const tcCommands = generateTcCommands();
    navigator.clipboard.writeText(tcCommands);
    setMessage({ type: 'success', text: 'TC commands copied to clipboard' });
  };

  // Group devices by cluster - include all clusters even if they have no devices
  const devicesByCluster = new Map<number, { cluster: Cluster; devices: Device[] }>();

  // First, add all clusters
  clusters.forEach(cluster => {
    devicesByCluster.set(cluster.id, { cluster, devices: [] });
  });

  // Then, add devices to their respective clusters
  devices.forEach(device => {
    const clusterEntry = devicesByCluster.get(device.cluster_id);
    if (clusterEntry) {
      clusterEntry.devices.push(device);
    }
  });

  // Helper function to check if a container is running
  const isContainerRunning = (containerName: string): boolean => {
    if (!containerStatus) return false;
    return containerStatus.running_containers.some(c => c.name === containerName && c.status === 'running');
  };

  // Get container statuses
  const frontendRunning = isContainerRunning('frontend');
  const backendRunning = isContainerRunning('backend');
  const routerRunning = isContainerRunning('router');
  const runningClientsCount = containerStatus?.devices.filter(d => d.status === 'running').length || 0;

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">
          Traffic Shaping Rules
        </h2>
        <div className="flex items-center gap-6">
          {/* Container Status Monitor */}
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <div className="flex items-center gap-1.5">
              <div className={`h-2 w-2 rounded-full ${frontendRunning ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span>Frontend</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className={`h-2 w-2 rounded-full ${backendRunning ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span>Backend</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className={`h-2 w-2 rounded-full ${routerRunning ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span>Router</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className={`h-2 w-2 rounded-full ${runningClientsCount > 0 ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span>Clients ({runningClientsCount})</span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-4">
            <button
              onClick={handleKillAllContainers}
              disabled={loading === 'kill-all'}
              className="text-sm text-red-400 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading === 'kill-all' ? 'Killing...' : 'Kill All Containers'}
            </button>
            <button
              onClick={handleAddCluster}
              disabled={loading !== null || editingCluster !== null}
              className="text-sm text-blue-400 hover:text-blue-300 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              + Add Cluster
            </button>
            <button
              onClick={() => setShowModal(true)}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              Copy Rules
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-2 text-slate-300 font-medium text-sm w-auto">Device</th>
              <th className="text-center py-2 px-2 text-slate-300 font-medium text-sm whitespace-nowrap">Type</th>
              <th className="text-center py-2 px-2 text-slate-300 font-medium text-sm whitespace-nowrap">Status</th>
              <th className="text-center py-2 px-2 text-slate-300 font-medium text-sm whitespace-nowrap">Interface</th>
              <th className="text-center py-2 px-1 text-orange-400 font-medium text-sm whitespace-nowrap" colSpan={2}>
                ↑ Upstream
              </th>
              <th className="text-center py-2 px-1 text-green-400 font-medium text-sm whitespace-nowrap" colSpan={2}>
                ↓ Downstream
              </th>
              <th className="text-center py-2 px-1 text-purple-400 font-medium text-sm whitespace-nowrap">
                Traffic
              </th>
              <th className="text-center py-2 px-2 text-slate-300 font-medium text-sm whitespace-nowrap">Actions</th>
            </tr>
            <tr className="border-b border-slate-700 text-xs">
              <th className="text-left py-1 px-2"></th>
              <th className="text-center py-1 px-2"></th>
              <th className="text-center py-1 px-2"></th>
              <th className="text-center py-1 px-2"></th>
              <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Rate</th>
              <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Ceil</th>
              <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Rate</th>
              <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Ceil</th>
              <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Amount</th>
              <th className="text-center py-1 px-2"></th>
            </tr>
          </thead>
          <tbody>
            {Array.from(devicesByCluster.values()).map(({ cluster, devices: clusterDevices }) => {
              const syncPreview = syncPreviews.get(cluster.id);
              const needsSync = syncPreview && syncPreview.total_changes > 0;

              return (
                <>
                  {/* Cluster header row */}
                  <tr key={`cluster-${cluster.id}`} className="group bg-slate-700">
                    <td colSpan={10} className="py-2 px-2">
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-slate-200">{cluster.name}</span>
                        <button
                          onClick={() => handleAddDevice(cluster.id)}
                          disabled={loading !== null}
                          className="text-blue-400 hover:text-blue-300 text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          + Device
                        </button>
                        {needsSync && (
                          <button
                            onClick={() => handleSyncCluster(cluster.id)}
                            disabled={loading === `sync-${cluster.id}`}
                            className="text-yellow-400 hover:text-yellow-300 text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                            title={`Sync needed: ${syncPreview.total_changes} changes`}
                          >
                            {loading === `sync-${cluster.id}` ? 'Syncing...' : '⟳ Sync'}
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteCluster(cluster)}
                          disabled={loading === `cluster-${cluster.id}`}
                          className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                          title="Delete cluster"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>

                  {/* Device editing row */}
                  {editingDevice && editingDevice.clusterId === cluster.id && (
                    <tr className="bg-blue-900/20 border-b border-blue-500/50">
                      <td className="py-1.5 px-2">
                        <input
                          type="text"
                          value={editingDevice.name}
                          onChange={(e) => setEditingDevice({ ...editingDevice, name: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveDevice();
                            if (e.key === 'Escape') handleCancelDeviceEdit();
                          }}
                          placeholder="Device name"
                          className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm"
                          autoFocus
                        />
                      </td>
                      <td className="py-1.5 px-2">
                        <select
                          value={editingDevice.deviceType}
                          onChange={(e) => setEditingDevice({ ...editingDevice, deviceType: e.target.value })}
                          className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm"
                        >
                          <option value="pc">PC</option>
                          <option value="mobile">Mobile</option>
                          <option value="server">Server</option>
                          <option value="iot">IoT</option>
                        </select>
                      </td>
                      <td colSpan={7} className="py-1.5 px-2 text-center text-slate-400 text-xs">
                        Disabled until saved
                      </td>
                      <td className="py-1.5 px-2">
                        <div className="flex gap-1 justify-center">
                          <button
                            onClick={handleSaveDevice}
                            disabled={!editingDevice.name || loading === 'device-edit'}
                            className="bg-green-600 hover:bg-green-700 disabled:bg-green-800 text-white text-xs font-medium py-1 px-2 rounded"
                          >
                            {loading === 'device-edit' ? 'Saving...' : 'Save'}
                          </button>
                          <button
                            onClick={handleCancelDeviceEdit}
                            className="bg-slate-600 hover:bg-slate-700 text-white text-xs font-medium py-1 px-2 rounded"
                          >
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}

                  {/* No devices placeholder */}
                  {clusterDevices.length === 0 && (!editingDevice || editingDevice.clusterId !== cluster.id) && (
                    <tr className="border-b border-slate-700/50">
                      <td colSpan={10} className="py-3 px-2 text-center text-slate-400 text-sm italic">
                        No devices. Click "+ Device" to add one.
                      </td>
                    </tr>
                  )}

                  {/* Device rows */}
                  {clusterDevices.map((device) => {
                    const state = clientStates[device.name] || {
                      upRate: '', upCeil: '', downRate: '', downCeil: '',
                      trafficAmount: '50M', trafficRunning: false
                    };
                    const isLoading = loading === device.name;
                    const isOnline = device.status === 'running';
                    const isDisabled = isLoading || !isOnline;
                    const isUnsynced = !device.interface_name && device.status !== 'error';

                    let statusText = 'Offline';
                    let statusColor = 'text-red-400';
                    if (device.status === 'running') {
                      statusText = 'Online';
                      statusColor = 'text-green-400';
                    } else if (device.status === 'starting') {
                      statusText = 'Starting';
                      statusColor = 'text-yellow-400';
                    } else if (device.status === 'stopping') {
                      statusText = 'Stopping';
                      statusColor = 'text-orange-400';
                    } else if (device.status === 'error') {
                      statusText = 'Error';
                      statusColor = 'text-red-500';
                    }

                    return (
                      <tr
                        key={device.id}
                        className={`group border-b border-slate-700/50 hover:bg-slate-700/30 ${
                          isUnsynced ? 'bg-amber-900/20' : ''
                        }`}
                      >
                        <td className="py-1.5 px-2 text-left">
                          <div className="flex items-center gap-2">
                            <div className="font-medium text-blue-400">{device.name}</div>
                            <button
                              onClick={() => handleDeleteDevice(device)}
                              disabled={loading === `device-${device.id}`}
                              className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                              title="Delete device"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </td>

                        <td className="py-1.5 px-2 text-center">
                          <span className="text-xs bg-slate-600 px-2 py-1 rounded text-slate-300">
                            {device.device_type}
                          </span>
                        </td>

                        <td className="py-1.5 px-2 text-center whitespace-nowrap">
                          <div className={`font-medium text-xs ${statusColor}`}>{statusText}</div>
                        </td>

                        <td className="py-1.5 px-2 text-center whitespace-nowrap">
                          <div className="text-xs text-slate-400">{device.interface_name || '-'}</div>
                        </td>

                        <td className="py-1.5 px-1 text-center">
                          <input
                            type="text"
                            value={state.upRate}
                            onChange={(e) => updateClientState(device.name, 'upRate', e.target.value)}
                            placeholder="20mbit"
                            disabled={isDisabled}
                            className="w-20 bg-slate-700 border border-slate-600 rounded px-1.5 py-0.5 text-white text-center text-sm focus:outline-none focus:ring-1 focus:ring-orange-500 disabled:opacity-50"
                          />
                        </td>

                        <td className="py-1.5 px-1 text-center">
                          <input
                            type="text"
                            value={state.upCeil}
                            onChange={(e) => updateClientState(device.name, 'upCeil', e.target.value)}
                            placeholder="50mbit"
                            disabled={isDisabled}
                            className="w-20 bg-slate-700 border border-slate-600 rounded px-1.5 py-0.5 text-white text-center text-sm focus:outline-none focus:ring-1 focus:ring-orange-500 disabled:opacity-50"
                          />
                        </td>

                        <td className="py-1.5 px-1 text-center">
                          <input
                            type="text"
                            value={state.downRate}
                            onChange={(e) => updateClientState(device.name, 'downRate', e.target.value)}
                            placeholder="20mbit"
                            disabled={isDisabled}
                            className="w-20 bg-slate-700 border border-slate-600 rounded px-1.5 py-0.5 text-white text-center text-sm focus:outline-none focus:ring-1 focus:ring-green-500 disabled:opacity-50"
                          />
                        </td>

                        <td className="py-1.5 px-1 text-center">
                          <input
                            type="text"
                            value={state.downCeil}
                            onChange={(e) => updateClientState(device.name, 'downCeil', e.target.value)}
                            placeholder="50mbit"
                            disabled={isDisabled}
                            className="w-20 bg-slate-700 border border-slate-600 rounded px-1.5 py-0.5 text-white text-center text-sm focus:outline-none focus:ring-1 focus:ring-green-500 disabled:opacity-50"
                          />
                        </td>

                        <td className="py-1.5 px-1 text-center">
                          <input
                            type="text"
                            value={state.trafficAmount}
                            onChange={(e) => updateClientState(device.name, 'trafficAmount', e.target.value)}
                            placeholder="50M"
                            disabled={isDisabled}
                            className="w-16 bg-slate-700 border border-slate-600 rounded px-1.5 py-0.5 text-white text-center text-sm focus:outline-none focus:ring-1 focus:ring-purple-500 disabled:opacity-50"
                          />
                        </td>

                        <td className="py-1.5 px-2 text-center">
                          <div className="flex gap-1 justify-center">
                            <button
                              onClick={() => handleApply(device)}
                              disabled={isDisabled}
                              className="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-800 text-white text-xs font-medium py-1 px-2 rounded transition-colors"
                              title="Apply rule"
                            >
                              Apply
                            </button>
                            <button
                              onClick={() => handleReset(device.name)}
                              disabled={isDisabled}
                              className="bg-slate-600 hover:bg-slate-700 disabled:bg-slate-800 text-white text-xs font-medium py-1 px-2 rounded transition-colors"
                              title="Reset to unlimited"
                            >
                              Reset
                            </button>
                            <button
                              onClick={() => handleToggleTraffic(device.name)}
                              disabled={isDisabled}
                              className={`${
                                state.trafficRunning
                                  ? 'bg-red-600 hover:bg-red-700 disabled:bg-slate-800'
                                  : 'bg-purple-600 hover:bg-purple-700 disabled:bg-slate-800'
                              } text-white text-xs font-medium py-1 px-2 rounded transition-colors`}
                              title={state.trafficRunning ? 'Stop traffic' : 'Start traffic'}
                            >
                              {state.trafficRunning ? 'Stop' : 'Start'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </>
              );
            })}

            {/* Cluster editing row */}
            {editingCluster && (
              <tr className="bg-blue-900/20 border-b border-blue-500/50">
                <td className="py-1.5 px-2" colSpan={2}>
                  <input
                    type="text"
                    value={editingCluster.name}
                    onChange={(e) => setEditingCluster({ ...editingCluster, name: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveCluster();
                      if (e.key === 'Escape') handleCancelClusterEdit();
                    }}
                    placeholder="Cluster name"
                    className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm"
                    autoFocus
                  />
                </td>
                <td className="py-1.5 px-2" colSpan={6}>
                  <input
                    type="text"
                    value={editingCluster.description}
                    onChange={(e) => setEditingCluster({ ...editingCluster, description: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveCluster();
                      if (e.key === 'Escape') handleCancelClusterEdit();
                    }}
                    placeholder="Description (optional)"
                    className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm"
                  />
                </td>
                <td className="py-1.5 px-2" colSpan={2}>
                  <div className="flex gap-1 justify-center">
                    <button
                      onClick={handleSaveCluster}
                      disabled={!editingCluster.name || loading === 'cluster-edit'}
                      className="bg-green-600 hover:bg-green-700 disabled:bg-green-800 text-white text-xs font-medium py-1 px-2 rounded"
                    >
                      {loading === 'cluster-edit' ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={handleCancelClusterEdit}
                      className="bg-slate-600 hover:bg-slate-700 text-white text-xs font-medium py-1 px-2 rounded"
                    >
                      Cancel
                    </button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-end justify-between">
        <div className="text-xs text-slate-400">
          <p>• Shaping: Use mbit format (10mbit, 50mbit, 100mbit) for Rate and Ceil</p>
          <p>• Traffic: Use M format (10M, 50M, 100M) for iperf3 bandwidth</p>
          <p>• Rate = guaranteed minimum, Ceil = maximum burst</p>
        </div>
        {message && (
          <span className={`text-sm ${
            message.type === 'success' ? 'text-green-400' : 'text-red-400'
          }`}>
            {message.text}
          </span>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowModal(false)}>
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 max-w-2xl w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Current Applied Rules</h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="bg-slate-900 border border-slate-700 rounded p-4 mb-4 max-h-96 overflow-y-auto">
              <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap">
                {rules.length > 0 ? generateTcCommands() : 'No rules currently applied'}
              </pre>
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowModal(false)}
                className="bg-slate-600 hover:bg-slate-700 text-white text-sm font-medium py-2 px-4 rounded transition-colors"
              >
                Close
              </button>
              <button
                onClick={handleCopyRules}
                className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2 px-4 rounded transition-colors"
              >
                Copy to Clipboard
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
