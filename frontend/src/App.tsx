import { useState } from 'react';
import Dashboard from './components/Dashboard';
import ClusterManager from './components/ClusterManager';

type View = 'dashboard' | 'clusters';

function App() {
  const [currentView, setCurrentView] = useState<View>('dashboard');

  return (
    <div className="min-h-screen bg-slate-900">
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-2xl font-bold text-white">
            QC Network Traffic Shaping
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Real-time network traffic monitoring and control
          </p>

          {/* Navigation Tabs */}
          <div className="mt-4 flex space-x-2">
            <button
              onClick={() => setCurrentView('dashboard')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                currentView === 'dashboard'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => setCurrentView('clusters')}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                currentView === 'clusters'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Cluster Management
            </button>
          </div>
        </div>
      </header>
      <main>
        {currentView === 'dashboard' ? <Dashboard /> : <ClusterManager />}
      </main>
    </div>
  );
}

export default App;
