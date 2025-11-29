import { useState } from 'react';
import Dashboard from './components/Dashboard';
import ClusterManager from './components/ClusterManager';

type View = 'dashboard' | 'clusters';

function App() {
  const [currentView, setCurrentView] = useState<View>('dashboard');

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

          {/* Navigation Tabs */}
          <div className="flex gap-2">
            <button
              onClick={() => setCurrentView('dashboard')}
              className={`px-4 py-2 rounded font-medium transition-colors ${
                currentView === 'dashboard'
                  ? 'bg-slate-700 text-blue-400'
                  : 'text-slate-400 hover:text-slate-300 hover:bg-slate-700/50'
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => setCurrentView('clusters')}
              className={`px-4 py-2 rounded font-medium transition-colors ${
                currentView === 'clusters'
                  ? 'bg-slate-700 text-blue-400'
                  : 'text-slate-400 hover:text-slate-300 hover:bg-slate-700/50'
              }`}
            >
              Cluster Management
            </button>
          </div>
        </div>
      </header>
      <main className="px-6">
        {currentView === 'dashboard' ? <Dashboard /> : <ClusterManager />}
      </main>
    </div>
  );
}

export default App;
