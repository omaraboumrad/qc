import Dashboard from './components/Dashboard';
import { useSSE } from './hooks/useSSE';

function App() {
  const { data, isConnected } = useSSE();

  return (
    <div className="min-h-screen bg-slate-900">
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">
              QC Network Traffic Shaping
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Real-time network traffic monitoring and control
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <div className={`h-3 w-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
            <span className="text-sm text-slate-400">
              {isConnected ? 'Live' : 'Disconnected'}
              {data && ` • Last update: ${new Date(data.timestamp * 1000).toLocaleTimeString()}`}
            </span>
          </div>
        </div>
      </header>
      <main className="px-6">
        <Dashboard />
      </main>
    </div>
  );
}

export default App;
