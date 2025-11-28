import { useState, useEffect } from 'react';
import { TrafficRule, BandwidthRule } from '../types/metrics';
import { apiService } from '../services/api';

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

export default function RulesPanel({ rules }: Props) {
  const clients = [
    { name: 'pc1', interface: 'eth1' },
    { name: 'pc2', interface: 'eth2' },
    { name: 'mb1', interface: 'eth3' },
    { name: 'mb2', interface: 'eth4' },
  ];

  const [clientStates, setClientStates] = useState<Record<string, ClientState>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showModal, setShowModal] = useState(false);

  // Initialize state from current rules
  useEffect(() => {
    setClientStates(prev => {
      const newStates: Record<string, ClientState> = {};
      clients.forEach(client => {
        const rule = rules.find(r => r.client === client.name);
        const existingState = prev[client.name];

        // Helper to clean up bandwidth values: hide "1Gbit" or "1gbit", keep others
        const cleanBandwidth = (value?: string) => {
          if (!value) return '';
          const normalized = value.replace('Mbit', 'mbit');
          // Hide unlimited bandwidth (1Gbit) from display
          if (normalized === '1gbit' || normalized === '1Gbit') return '';
          return normalized;
        };

        newStates[client.name] = {
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
  }, [rules]);

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

  const handleApply = async (clientName: string) => {
    setLoading(clientName);
    setMessage(null);

    try {
      const client = clients.find(c => c.name === clientName);
      if (!client) throw new Error('Client not found');

      const state = clientStates[clientName];

      // Default empty values to unlimited (1gbit)
      const rule: BandwidthRule = {
        interface: client.interface,
        client: client.name,
        class_id: '1:30',
        downstream_rate: state.downRate || '1gbit',
        downstream_ceil: state.downCeil || '1gbit',
        upstream_rate: state.upRate || '1gbit',
        upstream_ceil: state.upCeil || '1gbit',
        description: `Bidirectional rule for ${client.name}`,
      };

      await apiService.applySingleRule(rule);
      setMessage({
        type: 'success',
        text: `Rule applied to ${client.name}`
      });
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleReset = async (clientName: string) => {
    setLoading(clientName);
    setMessage(null);

    try {
      await apiService.deleteRule(clientName);
      setMessage({ type: 'success', text: `${clientName} reset to unlimited` });
    } catch (error: any) {
      setMessage({ type: 'error', text: error.response?.data?.detail || error.message });
    } finally {
      setLoading(null);
    }
  };

  const handleToggleTraffic = async (clientName: string) => {
    setLoading(clientName);
    setMessage(null);

    try {
      const state = clientStates[clientName];

      if (state.trafficRunning) {
        // Stop traffic
        const response = await fetch(`http://localhost:8000/api/traffic/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client: clientName })
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to stop traffic');
        }

        setMessage({ type: 'success', text: `Stopped traffic for ${clientName}` });
      } else {
        // Start traffic
        const response = await fetch(`http://localhost:8000/api/traffic/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client: clientName,
            duration: 300,  // 5 minutes
            bandwidth: state.trafficAmount
          })
        });

        if (!response.ok) {
          const error = await response.json();
          throw new Error(error.detail || 'Failed to start traffic');
        }

        setMessage({ type: 'success', text: `Started traffic for ${clientName} at ${state.trafficAmount}` });
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || 'Failed to toggle traffic' });
    } finally {
      setLoading(null);
    }
  };

  const generateTcCommands = () => {
    const IFB_MAPPING: Record<string, string> = {
      'eth1': 'ifb11',
      'eth2': 'ifb12',
      'eth3': 'ifb13',
      'eth4': 'ifb14',
    };

    const commands: string[] = [];

    rules.forEach(rule => {
      // Downstream command (physical interface)
      const downRate = rule.downstream_rate || rule.rate || '1gbit';
      const downCeil = rule.downstream_ceil || rule.ceil || '1gbit';
      commands.push(
        `# ${rule.client} - Downstream (${rule.interface})`,
        `tc class change dev ${rule.interface} parent 1:1 classid 1:30 htb rate ${downRate} ceil ${downCeil}`
      );

      // Upstream command (IFB device)
      if (rule.upstream_rate || rule.upstream_ceil) {
        const ifbDevice = IFB_MAPPING[rule.interface];
        const upRate = rule.upstream_rate || '1gbit';
        const upCeil = rule.upstream_ceil || '1gbit';
        if (ifbDevice) {
          commands.push(
            `# ${rule.client} - Upstream (${ifbDevice})`,
            `tc class change dev ${ifbDevice} parent 2:1 classid 2:30 htb rate ${upRate} ceil ${upCeil}`
          );
        }
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

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-3 px-2 text-slate-300 font-medium">Client</th>
              <th className="text-center py-3 px-2 text-orange-400 font-medium" colSpan={2}>
                ↑ Upstream
              </th>
              <th className="text-center py-3 px-2 text-green-400 font-medium" colSpan={2}>
                ↓ Downstream
              </th>
              <th className="text-center py-3 px-2 text-purple-400 font-medium">
                Traffic
              </th>
              <th className="text-center py-3 px-2 text-slate-300 font-medium">Actions</th>
            </tr>
            <tr className="border-b border-slate-700 text-xs">
              <th className="py-2 px-2"></th>
              <th className="text-center py-2 px-2 text-slate-400">Rate</th>
              <th className="text-center py-2 px-2 text-slate-400">Ceil</th>
              <th className="text-center py-2 px-2 text-slate-400">Rate</th>
              <th className="text-center py-2 px-2 text-slate-400">Ceil</th>
              <th className="text-center py-2 px-2 text-slate-400">Amount</th>
              <th className="py-2 px-2"></th>
            </tr>
          </thead>
          <tbody>
            {clients.map((client) => {
              const state = clientStates[client.name] || {
                upRate: '', upCeil: '', downRate: '', downCeil: '',
                trafficAmount: '50M', trafficRunning: false
              };
              const isLoading = loading === client.name;

              return (
                <tr key={client.name} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="py-3 px-2">
                    <div className="font-medium text-blue-400">{client.name}</div>
                    <div className="text-xs text-slate-500">{client.interface}</div>
                  </td>

                  {/* Upstream Rate */}
                  <td className="py-3 px-2">
                    <input
                      type="text"
                      value={state.upRate}
                      onChange={(e) => updateClientState(client.name, 'upRate', e.target.value)}
                      placeholder="20mbit"
                      disabled={isLoading}
                      className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-center focus:outline-none focus:ring-1 focus:ring-orange-500 disabled:opacity-50"
                    />
                  </td>

                  {/* Upstream Ceil */}
                  <td className="py-3 px-2">
                    <input
                      type="text"
                      value={state.upCeil}
                      onChange={(e) => updateClientState(client.name, 'upCeil', e.target.value)}
                      placeholder="50mbit"
                      disabled={isLoading}
                      className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-center focus:outline-none focus:ring-1 focus:ring-orange-500 disabled:opacity-50"
                    />
                  </td>

                  {/* Downstream Rate */}
                  <td className="py-3 px-2">
                    <input
                      type="text"
                      value={state.downRate}
                      onChange={(e) => updateClientState(client.name, 'downRate', e.target.value)}
                      placeholder="20mbit"
                      disabled={isLoading}
                      className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-center focus:outline-none focus:ring-1 focus:ring-green-500 disabled:opacity-50"
                    />
                  </td>

                  {/* Downstream Ceil */}
                  <td className="py-3 px-2">
                    <input
                      type="text"
                      value={state.downCeil}
                      onChange={(e) => updateClientState(client.name, 'downCeil', e.target.value)}
                      placeholder="50mbit"
                      disabled={isLoading}
                      className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-center focus:outline-none focus:ring-1 focus:ring-green-500 disabled:opacity-50"
                    />
                  </td>

                  {/* Traffic Amount */}
                  <td className="py-3 px-2">
                    <input
                      type="text"
                      value={state.trafficAmount}
                      onChange={(e) => updateClientState(client.name, 'trafficAmount', e.target.value)}
                      placeholder="50M"
                      disabled={isLoading}
                      className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-center focus:outline-none focus:ring-1 focus:ring-purple-500 disabled:opacity-50"
                    />
                  </td>

                  {/* Action Buttons */}
                  <td className="py-3 px-2">
                    <div className="flex gap-1 justify-center">
                      <button
                        onClick={() => handleApply(client.name)}
                        disabled={isLoading}
                        className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white text-xs font-medium py-1 px-2 rounded transition-colors"
                        title="Apply rule"
                      >
                        Apply
                      </button>
                      <button
                        onClick={() => handleReset(client.name)}
                        disabled={isLoading}
                        className="bg-slate-600 hover:bg-slate-700 disabled:bg-slate-800 text-white text-xs font-medium py-1 px-2 rounded transition-colors"
                        title="Reset to unlimited"
                      >
                        Reset
                      </button>
                      <button
                        onClick={() => handleToggleTraffic(client.name)}
                        disabled={isLoading}
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
