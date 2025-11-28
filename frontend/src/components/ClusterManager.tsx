import { useState, useEffect } from 'react';
import { apiService } from '../services/api';
import { Cluster, Device, SyncPreview } from '../types/cluster';

export default function ClusterManager() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [selectedCluster, setSelectedCluster] = useState<Cluster | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [syncPreview, setSyncPreview] = useState<SyncPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form states
  const [showCreateCluster, setShowCreateCluster] = useState(false);
  const [showCreateDevice, setShowCreateDevice] = useState(false);
  const [newClusterName, setNewClusterName] = useState('');
  const [newClusterDesc, setNewClusterDesc] = useState('');
  const [newDeviceName, setNewDeviceName] = useState('');
  const [newDeviceType, setNewDeviceType] = useState('pc');

  useEffect(() => {
    loadClusters();
  }, []);

  useEffect(() => {
    if (selectedCluster) {
      loadDevices(selectedCluster.id);
      loadSyncPreview(selectedCluster.id);
    }
  }, [selectedCluster]);

  const loadClusters = async () => {
    try {
      const data = await apiService.getClusters();
      setClusters(data);
      if (data.length > 0 && !selectedCluster) {
        setSelectedCluster(data[0]);
      }
    } catch (err: any) {
      setError(`Failed to load clusters: ${err.message}`);
    }
  };

  const loadDevices = async (clusterId: number) => {
    try {
      const data = await apiService.getDevices(clusterId);
      setDevices(data);
    } catch (err: any) {
      setError(`Failed to load devices: ${err.message}`);
    }
  };

  const loadSyncPreview = async (clusterId: number) => {
    try {
      const preview = await apiService.getSyncPreview(clusterId);
      setSyncPreview(preview);
    } catch (err: any) {
      console.error('Failed to load sync preview:', err);
    }
  };

  const handleCreateCluster = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const newCluster = await apiService.createCluster({
        name: newClusterName,
        description: newClusterDesc,
        active: true,
      });

      setSuccessMessage(`Cluster "${newCluster.name}" created successfully!`);
      setShowCreateCluster(false);
      setNewClusterName('');
      setNewClusterDesc('');
      await loadClusters();
      setSelectedCluster(newCluster);

      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(`Failed to create cluster: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateDevice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCluster) return;

    setLoading(true);
    setError(null);

    try {
      const newDevice = await apiService.createDevice({
        cluster_id: selectedCluster.id,
        name: newDeviceName,
        device_type: newDeviceType,
      });

      setSuccessMessage(`Device "${newDevice.name}" created successfully! IP: ${newDevice.ip_address}`);
      setShowCreateDevice(false);
      setNewDeviceName('');
      setNewDeviceType('pc');
      await loadDevices(selectedCluster.id);
      await loadSyncPreview(selectedCluster.id);

      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(`Failed to create device: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteDevice = async (deviceId: number, deviceName: string) => {
    if (!confirm(`Delete device "${deviceName}"?\n\nThis will:\n1. Stop and remove the container\n2. Delete the device from the database\n\nAre you sure?`)) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await apiService.deleteDevice(deviceId);

      if (result.container_destroyed) {
        setSuccessMessage(`Device "${deviceName}" deleted and container destroyed successfully!`);
      } else if (result.error) {
        setSuccessMessage(`Device "${deviceName}" deleted from database, but container cleanup had an issue: ${result.error}`);
      } else {
        setSuccessMessage(`Device "${deviceName}" deleted successfully!`);
      }

      if (selectedCluster) {
        await loadDevices(selectedCluster.id);
        await loadSyncPreview(selectedCluster.id);
      }

      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(`Failed to delete device: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async () => {
    if (!selectedCluster) return;

    if (!confirm('Execute sync? This will create/destroy containers to match the desired state.')) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await apiService.executeSync(selectedCluster.id);

      const summary = [
        result.created.length > 0 ? `Created: ${result.created.length}` : null,
        result.destroyed.length > 0 ? `Destroyed: ${result.destroyed.length}` : null,
        result.errors.length > 0 ? `Errors: ${result.errors.length}` : null,
      ].filter(Boolean).join(', ');

      setSuccessMessage(`Sync complete! ${summary || 'No changes'}`);

      await loadDevices(selectedCluster.id);
      await loadSyncPreview(selectedCluster.id);

      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setError(`Failed to sync: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleActive = async (cluster: Cluster) => {
    setLoading(true);
    setError(null);

    try {
      if (cluster.active) {
        await apiService.deactivateCluster(cluster.id);
        setSuccessMessage(`Cluster "${cluster.name}" deactivated`);
      } else {
        await apiService.activateCluster(cluster.id);
        setSuccessMessage(`Cluster "${cluster.name}" activated`);
      }

      await loadClusters();
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(`Failed to toggle cluster: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCluster = async (cluster: Cluster) => {
    if (!confirm(`Delete cluster "${cluster.name}" and all its devices?\n\nThis will:\n1. Stop and remove all containers in this cluster\n2. Delete all devices from the database\n3. Remove the cluster from the database\n\nAre you sure?`)) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await apiService.deleteCluster(cluster.id);

      if (result.errors && result.errors.length > 0) {
        setSuccessMessage(`Cluster "${cluster.name}" deleted. Destroyed ${result.containers_destroyed} containers. ${result.errors.length} errors occurred.`);
      } else {
        setSuccessMessage(`Cluster "${cluster.name}" deleted successfully! Destroyed ${result.containers_destroyed} containers.`);
      }

      await loadClusters();
      if (selectedCluster?.id === cluster.id) {
        setSelectedCluster(null);
        setDevices([]);
      }

      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setError(`Failed to delete cluster: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKillAllContainers = async () => {
    if (!confirm('Kill ALL client containers?\n\nThis will:\n1. Stop and remove ALL QC client containers\n2. Update all device statuses to "stopped"\n3. Leave networks intact (they will be reused on next sync)\n\nAre you sure?')) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await apiService.killAllContainers();
      setSuccessMessage(`Killed ${result.containers_killed} containers successfully!`);

      // Reload devices to show updated statuses
      if (selectedCluster) {
        await loadDevices(selectedCluster.id);
      }

      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setError(`Failed to kill containers: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: Device['status']) => {
    switch (status) {
      case 'running': return 'bg-green-500';
      case 'starting': return 'bg-yellow-500 animate-pulse';
      case 'stopping': return 'bg-orange-500 animate-pulse';
      case 'stopped': return 'bg-gray-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Fixed position alerts - won't shift content */}
      {error && (
        <div className="fixed top-4 right-4 z-50 max-w-md bg-red-900/95 border border-red-500 text-red-200 px-4 py-3 rounded-lg shadow-lg">
          <button
            onClick={() => setError(null)}
            className="float-right ml-3 text-red-300 hover:text-red-100"
          >
            ✕
          </button>
          {error}
        </div>
      )}
      {successMessage && (
        <div className="fixed top-4 right-4 z-50 max-w-md bg-green-900/95 border border-green-500 text-green-200 px-4 py-3 rounded-lg shadow-lg">
          <button
            onClick={() => setSuccessMessage(null)}
            className="float-right ml-3 text-green-300 hover:text-green-100"
          >
            ✕
          </button>
          {successMessage}
        </div>
      )}

      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Cluster Management</h2>
          <p className="text-slate-400 text-sm mt-1">
            Manage device clusters and containers
          </p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={handleKillAllContainers}
            disabled={loading}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium disabled:opacity-50"
          >
            Kill All Containers
          </button>
          <button
            onClick={() => setShowCreateCluster(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium"
          >
            + New Cluster
          </button>
        </div>
      </div>

      {/* Create Cluster Modal */}
      {showCreateCluster && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-xl font-bold text-white mb-4">Create New Cluster</h3>
            <form onSubmit={handleCreateCluster}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Cluster Name
                </label>
                <input
                  type="text"
                  value={newClusterName}
                  onChange={(e) => setNewClusterName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
                  placeholder="e.g., production-cluster"
                  required
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Description
                </label>
                <input
                  type="text"
                  value={newClusterDesc}
                  onChange={(e) => setNewClusterDesc(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
                  placeholder="Optional description"
                />
              </div>
              <div className="flex space-x-3">
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:opacity-50"
                >
                  {loading ? 'Creating...' : 'Create'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateCluster(false)}
                  className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded font-medium"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Device Modal */}
      {showCreateDevice && selectedCluster && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-slate-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-xl font-bold text-white mb-4">
              Add Device to {selectedCluster.name}
            </h3>
            <form onSubmit={handleCreateDevice}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Device Name
                </label>
                <input
                  type="text"
                  value={newDeviceName}
                  onChange={(e) => setNewDeviceName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
                  placeholder="e.g., laptop-1"
                  required
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Device Type
                </label>
                <select
                  value={newDeviceType}
                  onChange={(e) => setNewDeviceType(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white"
                >
                  <option value="pc">PC</option>
                  <option value="mobile">Mobile</option>
                  <option value="server">Server</option>
                  <option value="iot">IoT</option>
                </select>
              </div>
              <div className="flex space-x-3">
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:opacity-50"
                >
                  {loading ? 'Creating...' : 'Create'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateDevice(false)}
                  className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded font-medium"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Clusters List */}
        <div className="lg:col-span-1">
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h3 className="text-lg font-semibold text-white mb-4">Clusters</h3>
            <div className="space-y-2">
              {clusters.map((cluster) => (
                <div
                  key={cluster.id}
                  onClick={() => setSelectedCluster(cluster)}
                  className={`p-3 rounded-lg cursor-pointer transition-colors ${
                    selectedCluster?.id === cluster.id
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <div className="font-medium">{cluster.name}</div>
                      <div className="text-xs opacity-75">
                        {cluster.device_count || 0} devices
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleToggleActive(cluster);
                      }}
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        cluster.active
                          ? 'bg-green-600 hover:bg-green-700'
                          : 'bg-gray-600 hover:bg-gray-700'
                      }`}
                    >
                      {cluster.active ? 'Active' : 'Inactive'}
                    </button>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteCluster(cluster);
                    }}
                    className="w-full px-2 py-1 bg-red-600/20 hover:bg-red-600/40 text-red-300 rounded text-xs font-medium"
                  >
                    Delete Cluster
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Devices & Sync */}
        <div className="lg:col-span-2 space-y-6">
          {selectedCluster ? (
            <>
              {/* Sync Preview */}
              {syncPreview && syncPreview.total_changes > 0 && (
                <div className="bg-yellow-900/20 border border-yellow-500 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-lg font-semibold text-yellow-200">
                      Sync Required
                    </h4>
                    <button
                      onClick={handleSync}
                      disabled={loading}
                      className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded font-medium disabled:opacity-50"
                    >
                      {loading ? 'Syncing...' : 'Sync Now'}
                    </button>
                  </div>
                  <div className="text-sm text-yellow-200 space-y-1">
                    {syncPreview.to_create.length > 0 && (
                      <div>To create: {syncPreview.to_create.join(', ')}</div>
                    )}
                    {syncPreview.to_destroy.length > 0 && (
                      <div>To destroy: {syncPreview.to_destroy.join(', ')}</div>
                    )}
                  </div>
                </div>
              )}

              {/* Devices List */}
              <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">
                    Devices in {selectedCluster.name}
                  </h3>
                  <button
                    onClick={() => setShowCreateDevice(true)}
                    className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded font-medium"
                  >
                    + Add Device
                  </button>
                </div>

                {devices.length === 0 ? (
                  <div className="text-center py-8 text-slate-400">
                    No devices yet. Click "Add Device" to create one.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {devices.map((device) => (
                      <div
                        key={device.id}
                        className="bg-slate-700 rounded-lg p-4"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center space-x-3 mb-2">
                              <div className={`h-3 w-3 rounded-full ${getStatusColor(device.status)}`}></div>
                              <div className="font-medium text-white">{device.name}</div>
                              <span className="text-xs bg-slate-600 px-2 py-1 rounded text-slate-300">
                                {device.device_type}
                              </span>
                            </div>
                            <div className="text-sm text-slate-400 space-y-1">
                              <div>IP: {device.ip_address}</div>
                              <div>Container: {device.container_name}</div>
                              {device.interface_name && (
                                <div>Interface: {device.interface_name}</div>
                              )}
                              {device.error_message && (
                                <div className="text-red-400">Error: {device.error_message}</div>
                              )}
                            </div>
                          </div>
                          <button
                            onClick={() => handleDeleteDevice(device.id, device.name)}
                            className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-sm font-medium"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-8 text-center">
              <p className="text-slate-400">Select a cluster to view devices</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
