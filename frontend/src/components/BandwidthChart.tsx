import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { MetricsSnapshot } from '../types/metrics';
import { apiService } from '../services/api';

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
}

interface Props {
  data: MetricsSnapshot;
}

// Color palette for different devices
const COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16',
  '#f97316', '#6366f1', '#14b8a6', '#f43f5e'
];

export default function BandwidthChart({ data }: Props) {
  const [history, setHistory] = useState<any[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceToCluster, setDeviceToCluster] = useState<Map<string, string>>(new Map());

  // Load clusters and devices
  useEffect(() => {
    const loadData = async () => {
      try {
        const clustersData = await apiService.getClusters();
        setClusters(clustersData);

        // Load devices for all clusters
        const allDevices: Device[] = [];
        const mapping = new Map<string, string>();

        for (const cluster of clustersData) {
          const clusterDevices = await apiService.getDevices(cluster.id);
          allDevices.push(...clusterDevices);

          // Map device name to cluster name
          clusterDevices.forEach(device => {
            mapping.set(device.name, cluster.name);
          });
        }

        setDevices(allDevices);
        setDeviceToCluster(mapping);
      } catch (err) {
        console.error('Failed to load clusters/devices:', err);
      }
    };

    loadData();
  }, []);

  // Update history when new data arrives
  useEffect(() => {
    if (!data || !data.interfaces) return;

    const time = new Date(data.timestamp * 1000).toLocaleTimeString();
    const newPoint: any = { time };

    // Dynamically add data for each interface
    Object.entries(data.interfaces).forEach(([interfaceName, interfaceData]) => {
      const deviceName = interfaceData.client;

      // Downstream
      newPoint[`${deviceName}_down`] =
        interfaceData.downstream?.bandwidth_mbps ||
        interfaceData.bandwidth_mbps ||
        0;

      // Upstream
      newPoint[`${deviceName}_up`] =
        interfaceData.upstream?.bandwidth_mbps ||
        0;
    });

    setHistory((prev) => {
      const updated = [...prev, newPoint];
      // Keep last 60 data points (1 minute at 1/sec)
      return updated.slice(-60);
    });
  }, [data]);

  // Get active devices from current metrics (these are online)
  const activeDevices = data?.interfaces
    ? Object.values(data.interfaces).map(iface => iface.client)
    : [];

  // Get all devices grouped by cluster (to show online vs total)
  const allDevicesByCluster = new Map<number, { cluster: string; online: string[]; offline: string[]; total: number }>();
  devices.forEach(device => {
    const cluster = deviceToCluster.get(device.name) || 'Unknown';
    const clusterId = device.cluster_id;

    if (!allDevicesByCluster.has(clusterId)) {
      allDevicesByCluster.set(clusterId, { cluster, online: [], offline: [], total: 0 });
    }

    const group = allDevicesByCluster.get(clusterId)!;
    group.total++;

    if (activeDevices.includes(device.name)) {
      group.online.push(device.name);
    } else {
      group.offline.push(device.name);
    }
  });

  // Group active devices by cluster for chart display
  const devicesByCluster = new Map<string, string[]>();
  activeDevices.forEach(deviceName => {
    const clusterName = deviceToCluster.get(deviceName) || 'Unknown';
    if (!devicesByCluster.has(clusterName)) {
      devicesByCluster.set(clusterName, []);
    }
    devicesByCluster.get(clusterName)!.push(deviceName);
  });

  // Assign colors to devices
  const deviceColors = new Map<string, string>();
  activeDevices.forEach((device, index) => {
    deviceColors.set(device, COLORS[index % COLORS.length]);
  });

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <h2 className="text-lg font-semibold text-white mb-4">
        Bandwidth Usage (Mbps)
      </h2>

      {/* Cluster/Device Legend with Status */}
      <div className="mb-4 space-y-2">
        {Array.from(allDevicesByCluster.values()).map((group) => (
          <div key={group.cluster} className="text-sm">
            <span className="text-slate-400 font-medium">{group.cluster}</span>
            <span className="text-slate-500 ml-2 text-xs">
              ({group.online.length} online / {group.total} total)
            </span>
            <div className="ml-4 mt-1">
              {/* Online devices */}
              {group.online.length > 0 && (
                <div>
                  <span className="text-green-400 text-xs">● Online:</span>{' '}
                  {group.online.map((device, idx) => (
                    <span key={device}>
                      <span
                        className="font-medium"
                        style={{ color: deviceColors.get(device) }}
                      >
                        {device}
                      </span>
                      {idx < group.online.length - 1 ? ', ' : ''}
                    </span>
                  ))}
                </div>
              )}
              {/* Offline devices */}
              {group.offline.length > 0 && (
                <div className="mt-1">
                  <span className="text-red-400 text-xs">● Offline:</span>{' '}
                  {group.offline.map((device, idx) => (
                    <span key={device} className="text-slate-500">
                      {device}
                      {idx < group.offline.length - 1 ? ', ' : ''}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mb-2 text-xs text-slate-400">
        Solid lines: ↓ Downstream (Router → Client) | Dashed lines: ↑ Upstream (Client → Router)
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={history}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="time"
            stroke="#9ca3af"
            tick={{ fontSize: 12 }}
          />
          <YAxis
            stroke="#9ca3af"
            tick={{ fontSize: 12 }}
            label={{ value: 'Mbps', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af' } }}
            domain={[0, dataMax => (dataMax < 10 ? 100 : Math.ceil(dataMax * 1.1))]}
            tickFormatter={(value) => value.toFixed(0)}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
            labelStyle={{ color: '#e2e8f0' }}
            content={({ active, payload, label }) => {
              if (!active || !payload) return null;

              const formatVal = (val: number) => val < 1 ? val.toFixed(2) : val.toFixed(1);

              // Group data by device
              const deviceData: Record<string, { down: number; up: number }> = {};

              activeDevices.forEach(device => {
                const downEntry = payload.find(p => p.dataKey === `${device}_down`);
                const upEntry = payload.find(p => p.dataKey === `${device}_up`);
                deviceData[device] = {
                  down: downEntry ? Number(downEntry.value) : 0,
                  up: upEntry ? Number(upEntry.value) : 0
                };
              });

              return (
                <div className="bg-slate-800 border border-slate-600 p-3 rounded text-xs max-w-xs">
                  <p className="text-slate-300 mb-2 font-medium">{label}</p>
                  {Array.from(devicesByCluster.entries()).map(([clusterName, devices]) => (
                    <div key={clusterName} className="mb-2">
                      <p className="text-slate-400 text-[10px] mb-1">{clusterName}</p>
                      {devices.map(device => (
                        <div key={device} className="flex items-center gap-2 text-slate-200 ml-2">
                          <span
                            className="font-medium w-20 truncate"
                            style={{ color: deviceColors.get(device) }}
                          >
                            {device}
                          </span>
                          <span className="text-orange-400">↑ {formatVal(deviceData[device]?.up || 0)}</span>
                          <span className="text-green-400">↓ {formatVal(deviceData[device]?.down || 0)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              );
            }}
          />
          <Legend />

          {/* Dynamically generate lines for each device */}
          {activeDevices.map((device) => {
            const color = deviceColors.get(device);
            return (
              <Line
                key={`${device}_down`}
                type="monotone"
                dataKey={`${device}_down`}
                name={`${device} ↓`}
                stroke={color}
                strokeWidth={2}
                dot={false}
              />
            );
          })}
          {activeDevices.map((device) => {
            const color = deviceColors.get(device);
            return (
              <Line
                key={`${device}_up`}
                type="monotone"
                dataKey={`${device}_up`}
                name={`${device} ↑`}
                stroke={color}
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>

      {activeDevices.length === 0 && (
        <div className="text-center text-slate-400 py-8">
          No active devices. Create and sync devices in the Cluster Manager.
        </div>
      )}
    </div>
  );
}
