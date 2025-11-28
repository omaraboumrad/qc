import { useState, useEffect } from 'react';
import { TrafficRule, BandwidthRule } from '../types/metrics';
import { apiService } from '../services/api';

interface Props {
  rules: TrafficRule[];
}

interface Cluster {
  id: number;
  name: string;
  active: boolean;
}

interface Device {
  id: number;
  name: string;
  cluster_id: number;
  status: string;
  interface_name?: string;
  ifb_device?: string;
}

interface ClientState {
  upRate: string;
  upCeil: string;
  downRate: string;
  downCeil: string;
  trafficAmount: string;
  trafficRunning: boolean;
}

export default function RulesPanel({ rules }: Props) {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [clientStates, setClientStates] = useState<Record<string, ClientState>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showModal, setShowModal] = useState(false);

  // Load clusters and devices
  useEffect(() => {
    const loadData = async () => {
      try {
        const clustersData = await apiService.getClusters();
        setClusters(clustersData);

        // Load devices for all clusters (including offline ones)
        const allDevices: Device[] = [];
        for (const cluster of clustersData) {
          const clusterDevices = await apiService.getDevices(cluster.id);
          allDevices.push(...clusterDevices);
        }

        setDevices(allDevices);
      } catch (err) {
        console.error('Failed to load clusters/devices:', err);
      }
    };

    loadData();
    // Reload every 5 seconds to pick up new devices
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

        // Helper to clean up bandwidth values: hide "1Gbit" or "1gbit", keep others
        const cleanBandwidth = (value?: string) => {
          if (!value) return '';
          const normalized = value.replace('Mbit', 'mbit');
          // Hide unlimited bandwidth (1Gbit) from display
          if (normalized === '1gbit' || normalized === '1Gbit') return '';
          return normalized;
        };

        newStates[device.name] = {
          // Preserve existing user input if it exists, otherwise use rule values
          upRate: existingState?.upRate !== undefined ? existingState.upRate : cleanBandwidth(rule?.upstream_rate),
          upCeil: existingState?.upCeil !== undefined ? existingState.upCeil : cleanBandwidth(rule?.upstream_ceil),
          downRate: existingState?.downRate !== undefined ? existingState.downRate : cleanBandwidth(rule?.downstream_rate || rule?.rate),
          downCeil: existingState?.downCeil !== undefined ? existingState.downCeil : cleanBandwidth(rule?.downstream_ceil || rule?.ceil),
          // Preserve user-entered traffic amount and running state
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
        // Silently fail - traffic status is not critical
      }
    };

    checkTrafficStatus();
    const interval = setInterval(checkTrafficStatus, 2000);
    return () => clearInterval(interval);
  }, []);

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

      // Default empty values to unlimited (1gbit)
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
        // Stop traffic
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
        // Start traffic
        const response = await fetch(`http://localhost:8000/api/traffic/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client: deviceName,
            duration: 300,  // 5 minutes
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

  const generateTcCommands = () => {
    const commands: string[] = [];

    rules.forEach(rule => {
      // Find device to get IFB mapping
      const device = devices.find(d => d.name === rule.client);

      // Downstream command (physical interface)
      const downRate = rule.downstream_rate || rule.rate || '1gbit';
      const downCeil = rule.downstream_ceil || rule.ceil || '1gbit';
      commands.push(
        `# ${rule.client} - Downstream (${rule.interface})`,
        `tc class change dev ${rule.interface} parent 1:1 classid 1:30 htb rate ${downRate} ceil ${downCeil}`
      );

      // Upstream command (IFB device)
      if (device?.ifb_device && (rule.upstream_rate || rule.upstream_ceil)) {
        const upRate = rule.upstream_rate || '1gbit';
        const upCeil = rule.upstream_ceil || '1gbit';
        commands.push(
          `# ${rule.client} - Upstream (${device.ifb_device})`,
          `tc class change dev ${device.ifb_device} parent 2:1 classid 2:30 htb rate ${upRate} ceil ${upCeil}`
        );
      }

      commands.push(''); // Empty line between clients
    });

    return commands.join('\n');
  };

  const handleCopyRules = () => {
    const tcCommands = generateTcCommands();
    navigator.clipboard.writeText(tcCommands);
    setMessage({ type: 'success', text: 'TC commands copied to clipboard' });
  };

  // Group devices by cluster
  const devicesByCluster = new Map<number, { cluster: Cluster; devices: Device[] }>();
  devices.forEach(device => {
    const cluster = clusters.find(c => c.id === device.cluster_id);
    if (!cluster) return;

    if (!devicesByCluster.has(cluster.id)) {
      devicesByCluster.set(cluster.id, { cluster, devices: [] });
    }
    devicesByCluster.get(cluster.id)!.devices.push(device);
  });

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">
          Traffic Shaping Rules
        </h2>
        {message && (
          <span className={`text-sm ${
            message.type === 'success' ? 'text-green-400' : 'text-red-400'
          }`}>
            {message.text}
          </span>
        )}
      </div>

      {devices.length === 0 ? (
        <div className="text-center text-slate-400 py-8">
          No running devices found. Create and sync devices in the Cluster Manager.
        </div>
      ) : (
        <>
          {Array.from(devicesByCluster.values()).map(({ cluster, devices: clusterDevices }) => (
            <div key={cluster.id} className="mb-6">
              <h3 className="text-md font-medium text-slate-300 mb-3 border-b border-slate-700 pb-2">
                {cluster.name}
              </h3>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700">
                      <th className="text-left py-2 px-2 text-slate-300 font-medium text-sm w-auto">Device</th>
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
                      <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Rate</th>
                      <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Ceil</th>
                      <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Rate</th>
                      <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Ceil</th>
                      <th className="text-center py-1 px-1 text-slate-400 whitespace-nowrap">Amount</th>
                      <th className="text-center py-1 px-2"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {clusterDevices.map((device) => {
                      const state = clientStates[device.name] || {
                        upRate: '', upCeil: '', downRate: '', downCeil: '',
                        trafficAmount: '50M', trafficRunning: false
                      };
                      const isLoading = loading === device.name;
                      const isOnline = device.status === 'running';
                      const isDisabled = isLoading || !isOnline;

                      // Status display
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
                        <tr key={device.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                          {/* Device */}
                          <td className="py-1.5 px-2 text-left">
                            <div className="font-medium text-blue-400">{device.name}</div>
                          </td>

                          {/* Status */}
                          <td className="py-1.5 px-2 text-center whitespace-nowrap">
                            <div className={`font-medium text-xs ${statusColor}`}>{statusText}</div>
                          </td>

                          {/* Interface */}
                          <td className="py-1.5 px-2 text-center whitespace-nowrap">
                            <div className="text-xs text-slate-400">{device.interface_name || '-'}</div>
                          </td>

                          {/* Upstream Rate */}
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

                          {/* Upstream Ceil */}
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

                          {/* Downstream Rate */}
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

                          {/* Downstream Ceil */}
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

                          {/* Traffic Amount */}
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

                          {/* Action Buttons */}
                          <td className="py-1.5 px-2 text-center">
                            <div className="flex gap-1 justify-center">
                              <button
                                onClick={() => handleApply(device)}
                                disabled={isDisabled}
                                className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white text-xs font-medium py-1 px-2 rounded transition-colors"
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
                                    ? 'bg-red-600 hover:bg-red-700 disabled:bg-red-800'
                                    : 'bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800'
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
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </>
      )}

      <div className="mt-4 flex items-center justify-between">
        <div className="text-xs text-slate-400">
          <p>• Shaping: Use mbit format (10mbit, 50mbit, 100mbit) for Rate and Ceil</p>
          <p>• Traffic: Use M format (10M, 50M, 100M) for iperf3 bandwidth</p>
          <p>• Rate = guaranteed minimum, Ceil = maximum burst</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="text-sm text-blue-400 hover:text-blue-300 underline whitespace-nowrap"
        >
          Copy Rules
        </button>
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
