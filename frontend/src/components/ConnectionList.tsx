import { Connection } from '../types/metrics';

interface Props {
  connections: Connection[];
}

export default function ConnectionList({ connections }: Props) {
  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <h2 className="text-lg font-semibold text-white mb-4">
        Active Connections
      </h2>

      {connections.length === 0 ? (
        <div className="text-center py-8 text-slate-400">
          <p>No active connections</p>
          <p className="text-sm mt-1">Run iperf3 from a client to see connections</p>
        </div>
      ) : (
        <div className="space-y-3">
          {connections.map((conn, idx) => (
            <div key={idx} className="bg-slate-700/50 rounded-lg p-3 border border-slate-600">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-blue-400">{conn.client}</span>
                <span className="text-xs px-2 py-1 bg-green-500/20 text-green-400 rounded">
                  {conn.state}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="text-slate-400">Protocol</p>
                  <p className="text-white font-mono">{conn.protocol}</p>
                </div>
                <div>
                  <p className="text-slate-400">Remote</p>
                  <p className="text-white font-mono truncate">{conn.remote_addr}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
