import { useSSE } from '../hooks/useSSE';
import BandwidthChart from './BandwidthChart';
import RulesPanel from './RulesPanel';

export default function Dashboard() {
  const { data, error, isConnected } = useSSE();

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="bg-red-900/20 border border-red-500 text-red-200 px-4 py-3 rounded">
          <p className="font-bold">Connection Error</p>
          <p className="text-sm">{error.message}</p>
          <p className="text-xs mt-2">Make sure the backend is running on http://localhost:8000</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="bg-slate-800 border border-slate-700 px-4 py-3 rounded">
          <div className="flex items-center space-x-3">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500"></div>
            <p className="text-slate-300">Connecting to metrics stream...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8">
      {/* Connection Status */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <div className={`h-3 w-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span className="text-sm text-slate-400">
            {isConnected ? 'Live' : 'Disconnected'}
            {data && ` • Last update: ${new Date(data.timestamp * 1000).toLocaleTimeString()}`}
          </span>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 gap-6">
        {/* Traffic Shaping Rules */}
        <RulesPanel rules={data.rules} />

        {/* Bandwidth Chart */}
        <BandwidthChart data={data} />
      </div>
    </div>
  );
}
