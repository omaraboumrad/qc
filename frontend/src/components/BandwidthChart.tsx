import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { MetricsSnapshot } from '../types/metrics';

interface BandwidthDataPoint {
  time: string;
  // Downstream (router → client)
  pc1_down: number;
  pc2_down: number;
  mb1_down: number;
  mb2_down: number;
  // Upstream (client → router)
  pc1_up: number;
  pc2_up: number;
  mb1_up: number;
  mb2_up: number;
}

interface Props {
  data: MetricsSnapshot;
}

export default function BandwidthChart({ data }: Props) {
  const [history, setHistory] = useState<BandwidthDataPoint[]>([]);

  useEffect(() => {
    const time = new Date(data.timestamp * 1000).toLocaleTimeString();

    const newPoint: BandwidthDataPoint = {
      time,
      // Downstream bandwidth
      pc1_down: data.interfaces.eth1?.downstream?.bandwidth_mbps || data.interfaces.eth1?.bandwidth_mbps || 0,
      pc2_down: data.interfaces.eth2?.downstream?.bandwidth_mbps || data.interfaces.eth2?.bandwidth_mbps || 0,
      mb1_down: data.interfaces.eth3?.downstream?.bandwidth_mbps || data.interfaces.eth3?.bandwidth_mbps || 0,
      mb2_down: data.interfaces.eth4?.downstream?.bandwidth_mbps || data.interfaces.eth4?.bandwidth_mbps || 0,
      // Upstream bandwidth
      pc1_up: data.interfaces.eth1?.upstream?.bandwidth_mbps || 0,
      pc2_up: data.interfaces.eth2?.upstream?.bandwidth_mbps || 0,
      mb1_up: data.interfaces.eth3?.upstream?.bandwidth_mbps || 0,
      mb2_up: data.interfaces.eth4?.upstream?.bandwidth_mbps || 0,
    };

    setHistory((prev) => {
      const updated = [...prev, newPoint];
      // Keep last 60 data points (1 minute at 1/sec)
      return updated.slice(-60);
    });
  }, [data]);

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <h2 className="text-lg font-semibold text-white mb-4">
        Bandwidth Usage (Mbps)
      </h2>
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

              // Group by client
              const clients = ['pc1', 'pc2', 'mb1', 'mb2'];
              const data: Record<string, { down: number; up: number }> = {};

              clients.forEach(client => {
                const downEntry = payload.find(p => p.dataKey === `${client}_down`);
                const upEntry = payload.find(p => p.dataKey === `${client}_up`);
                data[client] = {
                  down: downEntry ? Number(downEntry.value) : 0,
                  up: upEntry ? Number(upEntry.value) : 0
                };
              });

              return (
                <div className="bg-slate-800 border border-slate-600 p-2 rounded text-xs">
                  <p className="text-slate-300 mb-1">{label}</p>
                  {clients.map(client => (
                    <div key={client} className="flex items-center gap-2 text-slate-200">
                      <span className="font-medium" style={{ color:
                        client === 'pc1' ? '#3b82f6' :
                        client === 'pc2' ? '#10b981' :
                        client === 'mb1' ? '#f59e0b' : '#ef4444'
                      }}>{client}</span>
                      <span className="text-orange-400">↑ {formatVal(data[client].up)}</span>
                      <span className="text-green-400">↓ {formatVal(data[client].down)}</span>
                    </div>
                  ))}
                </div>
              );
            }}
          />
          <Legend />
          {/* Downstream (solid lines) */}
          <Line type="monotone" dataKey="pc1_down" name="pc1 ↓" stroke="#3b82f6" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="pc2_down" name="pc2 ↓" stroke="#10b981" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="mb1_down" name="mb1 ↓" stroke="#f59e0b" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="mb2_down" name="mb2 ↓" stroke="#ef4444" strokeWidth={2} dot={false} />
          {/* Upstream (dashed lines) */}
          <Line type="monotone" dataKey="pc1_up" name="pc1 ↑" stroke="#3b82f6" strokeWidth={2} strokeDasharray="5 5" dot={false} />
          <Line type="monotone" dataKey="pc2_up" name="pc2 ↑" stroke="#10b981" strokeWidth={2} strokeDasharray="5 5" dot={false} />
          <Line type="monotone" dataKey="mb1_up" name="mb1 ↑" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 5" dot={false} />
          <Line type="monotone" dataKey="mb2_up" name="mb2 ↑" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 5" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
