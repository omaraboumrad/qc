import { MetricsSnapshot } from '../types/metrics';

interface Props {
  data: MetricsSnapshot;
}

export default function PacketStats({ data }: Props) {
  const interfaces = ['eth1', 'eth2', 'eth3', 'eth4'];

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <h2 className="text-lg font-semibold text-white mb-4">
        Packet Statistics
      </h2>
      <div className="space-y-4">
        {interfaces.map((iface) => {
          const stats = data.interfaces[iface];
          if (!stats) return null;

          return (
            <div key={iface} className="border-b border-slate-700 pb-3 last:border-0 last:pb-0">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-blue-400">{stats.client}</span>
                <span className="text-xs text-slate-500">{iface}</span>
              </div>

              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-slate-400 text-xs">Bandwidth</p>
                  <p className="text-white font-mono">{stats.bandwidth_mbps.toFixed(2)} Mbps</p>
                </div>
                <div>
                  <p className="text-slate-400 text-xs">Packets Sent</p>
                  <p className="text-white font-mono">{stats.packets_sent.toLocaleString()}</p>
                </div>
                <div>
                  <p className="text-slate-400 text-xs">Dropped</p>
                  <p className={`font-mono ${stats.packets_dropped > 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {stats.packets_dropped.toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Utilization bar */}
              <div className="mt-2">
                <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                  <span>Utilization</span>
                  <span>{stats.utilization_percent.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-slate-700 rounded-full h-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(stats.utilization_percent, 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
