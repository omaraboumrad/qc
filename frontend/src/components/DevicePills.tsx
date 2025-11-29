import { MetricsSnapshot } from '../types/metrics';

interface Props {
  data: MetricsSnapshot;
}

export default function DevicePills({ data }: Props) {
  // Extract device stats from interfaces
  const deviceStats = Object.values(data.interfaces).map(iface => ({
    name: iface.client,
    upstream: iface.upstream?.bandwidth_mbps || 0,
    downstream: iface.downstream?.bandwidth_mbps || 0,
  }));

  // Sort by name for consistent ordering
  deviceStats.sort((a, b) => a.name.localeCompare(b.name));

  if (deviceStats.length === 0) {
    return null;
  }

  const formatBandwidth = (mbps: number): string => {
    if (mbps === 0) return '0';
    if (mbps < 1) return `${(mbps * 1000).toFixed(0)}K`;
    if (mbps < 100) return mbps.toFixed(1);
    return mbps.toFixed(0);
  };

  return (
    <div className="grid grid-cols-6 gap-4 mb-6">
      {deviceStats.map((device) => (
        <div
          key={device.name}
          className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex flex-col items-center justify-center"
        >
          {/* Device Name */}
          <div className="text-lg font-semibold text-white mb-4 text-center truncate w-full" title={device.name}>
            {device.name}
          </div>

          {/* Bandwidth Stats */}
          <div className="flex items-center gap-4 text-base">
            {/* Upstream */}
            <div className="flex items-center gap-1">
              <span className="text-orange-400 text-xl">↑</span>
              <span className="text-orange-400 font-mono">
                {formatBandwidth(device.upstream)}
              </span>
            </div>

            {/* Downstream */}
            <div className="flex items-center gap-1">
              <span className="text-green-400 text-xl">↓</span>
              <span className="text-green-400 font-mono">
                {formatBandwidth(device.downstream)}
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
