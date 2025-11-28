import Dashboard from './components/Dashboard';

function App() {
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
        </div>
      </header>
      <main>
        <Dashboard />
      </main>
    </div>
  );
}

export default App;
