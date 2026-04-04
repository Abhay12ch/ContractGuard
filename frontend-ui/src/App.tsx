import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchContracts, uploadContract, fetchContractStatus, clearSession, type Contract } from './api';
import { ContractsView } from './components/ContractsView';
import { CompareView } from './components/CompareView';

// Individual Polling Component for the table rows
const ProcessingTableRow = ({ contract, isNewUpload }: { contract: Contract, isNewUpload?: boolean }) => {
  
  // Conditionally poll if status is parsing/indexing/queued
  const isProcessing = ['queued', 'parsing', 'indexing', 'processing'].includes(contract.status);
  
  const { data: liveStatus } = useQuery({
    queryKey: ['contractStatus', contract.id],
    queryFn: () => fetchContractStatus(contract.id),
    refetchInterval: isProcessing ? 2000 : false,
    initialData: { status: contract.status },
  });

  const currentStatus = liveStatus?.status || contract.status;
  const isNowProcessing = ['queued', 'parsing', 'indexing', 'processing'].includes(currentStatus);
  const isDone = currentStatus === 'ready';

  let progress = 0;
  if (currentStatus === 'queued') progress = 10;
  else if (currentStatus === 'parsing') progress = 40;
  else if (currentStatus === 'indexing') progress = 80;
  else if (currentStatus === 'ready') progress = 100;
  
  // Progress bar rendering
  return (
    <tr className="hover:bg-surface-container-low/30 transition-all group">
      <td className="px-8 py-6">
        <div className="flex items-center gap-3">
          <span className={`material-symbols-outlined ${contract.filename.endsWith('pdf') ? 'text-red-500' : 'text-blue-500'}`}>
            {contract.filename.endsWith('pdf') ? 'picture_as_pdf' : 'description'}
          </span>
          <span className="font-medium text-on-surface">{contract.filename}</span>
          {isNewUpload && <span className="ml-2 px-2 py-0.5 bg-tertiary-fixed text-on-tertiary-fixed rounded text-[10px] font-bold">NEW</span>}
        </div>
      </td>
      <td className="px-8 py-6">
        {isNowProcessing && (
          <span className="px-3 py-1 bg-blue-50 text-blue-600 rounded-full text-xs font-bold capitalize">
            {currentStatus}...
          </span>
        )}
        {isDone && (
          <span className="px-3 py-1 bg-emerald-50 text-emerald-600 rounded-full text-xs font-bold">
            Completed
          </span>
        )}
        {!isNowProcessing && !isDone && (
          <span className="px-3 py-1 bg-slate-100 text-slate-500 rounded-full text-xs font-bold capitalize">
            {currentStatus}
          </span>
        )}
      </td>
      <td className="px-8 py-6">
        <div className="w-32 bg-slate-100 h-1.5 rounded-full overflow-hidden">
          <div 
            className={`h-full transition-all duration-1000 ${isDone ? 'bg-emerald-500' : 'bg-primary'}`} 
            style={{ width: `${progress}%` }}
          ></div>
        </div>
      </td>
      <td className="px-8 py-6 text-right">
        {isDone && (
          <button className="p-2 text-slate-400 hover:text-primary transition-all">
            <span className="material-symbols-outlined">visibility</span>
          </button>
        )}
      </td>
    </tr>
  );
};


function App() {
  const [activeView, setActiveView] = useState<'dashboard' | 'vault' | 'compare'>('dashboard');
  const [newUploadIds, setNewUploadIds] = useState<string[]>([]);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch all contracts globally
  const { data: contracts = [], isLoading: isContractsLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: fetchContracts,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadContract,
    onSuccess: (data) => {
      setNewUploadIds((prev) => [data.contract_id, ...prev]);
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      uploadMutation.mutate(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      uploadMutation.mutate(e.target.files[0]);
    }
  };

  const clearMutation = useMutation({
    mutationFn: clearSession,
    onSuccess: () => {
      setNewUploadIds([]);
      setActiveView('dashboard');
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    }
  });

  const activeProcessing = contracts.filter(c => ['queued', 'parsing', 'indexing'].includes(c.status)).length;
  const verifiedCompleted = contracts.filter(c => c.status === 'ready').length;
  const anomalies = contracts.filter(c => c.status === 'error').length;

  // Render recent queue (prioritize new uploads, then processing, then recently completed)
  const queueToDisplay = [...contracts]
    .sort((a, b) => {
      if (newUploadIds.includes(a.id) && !newUploadIds.includes(b.id)) return -1;
      if (!newUploadIds.includes(a.id) && newUploadIds.includes(b.id)) return 1;
      return 0; // maintain original list order otherwise
    })
    .slice(0, 5);

  return (
    <div className="bg-background text-on-background font-body antialiased min-h-screen">
      {/* SideNavBar */}
      <aside className="fixed left-0 top-0 h-screen w-64 bg-slate-50 dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col py-8 px-4 z-[60]">
        <div className="mb-10 px-2">
          <div className="text-xl font-black text-teal-700 dark:text-teal-300 tracking-tighter">ContractGuard AI</div>
          <p className="text-[10px] font-label uppercase tracking-[0.2em] text-slate-500 mt-1">Clinical Architect v1.0</p>
        </div>
        
        <nav className="flex-1 space-y-1">
          <button 
            onClick={() => setActiveView('dashboard')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 transition-all text-left font-bold ${activeView === 'dashboard' ? 'text-teal-700 dark:text-teal-400 border-r-4 border-teal-600 bg-teal-50/50' : 'text-slate-500 dark:text-slate-400 hover:text-teal-600 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
          >
            <span className="material-symbols-outlined" style={{fontVariationSettings: "'FILL' 1"}}>dashboard</span>
            <span className="text-body-lg tracking-tight">Dashboard</span>
          </button>
          <button 
            onClick={() => setActiveView('vault')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 transition-all text-left font-bold ${activeView === 'vault' ? 'text-teal-700 dark:text-teal-400 border-r-4 border-teal-600 bg-teal-50/50' : 'text-slate-500 dark:text-slate-400 hover:text-teal-600 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
          >
            <span className="material-symbols-outlined">folder_open</span>
            <span className="text-body-lg tracking-tight">Vault</span>
          </button>
          <button 
            onClick={() => setActiveView('compare')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 transition-all text-left font-bold ${activeView === 'compare' ? 'text-teal-700 dark:text-teal-400 border-r-4 border-teal-600 bg-teal-50/50' : 'text-slate-500 dark:text-slate-400 hover:text-teal-600 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
          >
            <span className="material-symbols-outlined">compare_arrows</span>
            <span className="text-body-lg tracking-tight">Compare</span>
          </button>
        </nav>
        
        <div className="mt-auto px-2 space-y-2">
          <button 
            onClick={() => clearMutation.mutate()}
            disabled={clearMutation.isPending || contracts.length === 0}
            className="w-full py-3 bg-red-50 text-red-600 rounded-full font-bold shadow-sm hover:bg-red-100 disabled:opacity-50 transition-all flex items-center justify-center gap-2"
          >
            {clearMutation.isPending ? <span className="material-symbols-outlined animate-spin">refresh</span> : <><span className="material-symbols-outlined">delete</span> Clear Vault</>}
          </button>
          <button 
            onClick={() => fileInputRef.current?.click()}
            className="w-full py-3 bg-gradient-to-br from-primary to-primary-container text-on-primary rounded-full font-semibold shadow-lg shadow-primary/20 hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-2"
          >
            {uploadMutation.isPending ? <span className="material-symbols-outlined animate-spin">refresh</span> : 'New Upload'}
          </button>
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            accept=".pdf,.docx,.txt"
            onChange={handleFileSelect} 
          />
        </div>
      </aside>

      {/* TopNavBar */}
      <header className="fixed top-0 right-0 w-[calc(100%-16rem)] h-16 bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl z-50 flex justify-between items-center px-8 shadow-2xl shadow-slate-900/5 transition-opacity duration-300">
        <div className="flex items-center bg-surface-container-low rounded-full px-4 py-1.5 w-96">
          <span className="material-symbols-outlined text-slate-400 text-xl">search</span>
          <input className="bg-transparent border-none outline-none focus:ring-0 text-sm w-full placeholder:text-slate-400 ml-2" placeholder="Search contracts, risks, or entities..." type="text" />
        </div>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3 pl-6 border-l border-slate-200 dark:border-slate-800">
            <div className="text-right">
              <p className="text-xs font-bold text-slate-900 dark:text-white">Admin</p>
              <p className="text-[10px] text-slate-500 uppercase tracking-widest font-label">Lead Architect</p>
            </div>
            <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold">A</div>
          </div>
        </div>
      </header>

      {/* Main Content Canvas */}
      <main className="ml-64 pt-16 min-h-screen">
        <div className="max-w-7xl mx-auto px-8 py-12">
          
          {/* Hero Section */}
          <section className="relative mb-16">
            <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-8">
              <div className="max-w-2xl">
                <span className="text-xs font-label uppercase tracking-[0.3em] text-primary font-semibold mb-4 block">System Overview</span>
                <h1 className="text-4xl md:text-5xl font-extrabold text-on-background tracking-tight mb-4 leading-tight">Contract Intelligence Dashboard</h1>
                <p className="text-body-lg text-secondary leading-relaxed max-w-lg">
                  Leverage clinical-grade AI to parse, validate, and compare legal frameworks with 99.8% precision.
                </p>
              </div>
            </div>
            {/* AI Insight Widget */}
            <div className="mt-12 p-6 glass-effect bg-surface-container-low/70 rounded-lg border-l-4 border-primary shadow-2xl shadow-primary/5 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center">
                  <span className="material-symbols-outlined text-primary" style={{fontVariationSettings: "'FILL' 1"}}>psychology</span>
                </div>
                <div>
                  <h4 className="font-bold text-on-surface">API Status</h4>
                  <p className="text-secondary text-sm">
                    {isContractsLoading ? 'Syncing to Backend...' : 'Global systems synchronized with FastAPI node.'}
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* Stats Grid */}
          <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
            <div className="bg-surface-container-lowest p-6 rounded-lg shadow-sm border border-transparent hover:border-outline-variant/30 transition-all group">
              <div className="flex justify-between items-start mb-4">
                <div className="p-2 bg-slate-100 rounded-lg text-slate-600">
                  <span className="material-symbols-outlined">folder_zip</span>
                </div>
              </div>
              <p className="text-xs font-label uppercase tracking-widest text-secondary font-bold mb-1">Total Vault</p>
              <h3 className="text-3xl font-black text-on-surface">{contracts.length}</h3>
            </div>
            
            <div className="bg-surface-container-lowest p-6 rounded-lg shadow-sm border border-transparent hover:border-outline-variant/30 transition-all">
              <div className="flex justify-between items-start mb-4">
                <div className="p-2 bg-blue-50 rounded-lg text-blue-600">
                  <span className="material-symbols-outlined">sync</span>
                </div>
              </div>
              <p className="text-xs font-label uppercase tracking-widest text-secondary font-bold mb-1">Processing</p>
              <h3 className="text-3xl font-black text-on-surface">{activeProcessing}</h3>
            </div>
            
            <div className="bg-surface-container-lowest p-6 rounded-lg shadow-sm border border-transparent hover:border-outline-variant/30 transition-all">
              <div className="flex justify-between items-start mb-4">
                <div className="p-2 bg-emerald-50 rounded-lg text-emerald-600">
                  <span className="material-symbols-outlined">verified</span>
                </div>
              </div>
              <p className="text-xs font-label uppercase tracking-widest text-secondary font-bold mb-1">Completed</p>
              <h3 className="text-3xl font-black text-on-surface">{verifiedCompleted}</h3>
            </div>

            <div className="bg-surface-container-lowest p-6 rounded-lg shadow-sm border border-transparent hover:border-outline-variant/30 transition-all">
              <div className="flex justify-between items-start mb-4">
                <div className="p-2 bg-error-container/30 rounded-lg text-error">
                  <span className="material-symbols-outlined">report</span>
                </div>
              </div>
              <p className="text-xs font-label uppercase tracking-widest text-secondary font-bold mb-1">Anomalies</p>
              <h3 className="text-3xl font-black text-on-surface">{anomalies}</h3>
            </div>
          </section>

          {/* Conditional Rendering of Views */}
          {activeView === 'dashboard' && (
            <section className="mb-16">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-12 animate-in fade-in slide-in-from-bottom-4">
                {/* Left Column (Upload & Queue) */}
                <div className="lg:col-span-2 space-y-12">
                  {/* Drag and Drop */}
                  <div 
                    className="relative group"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleFileDrop}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <div className="absolute -inset-1 bg-gradient-to-r from-primary/20 to-primary-container/20 rounded-lg blur opacity-25 group-hover:opacity-100 transition duration-1000 group-hover:duration-200"></div>
                    <div className="relative bg-surface-container-lowest p-16 rounded-lg border-2 border-dashed border-outline-variant hover:border-primary transition-colors flex flex-col items-center justify-center text-center cursor-pointer">
                      <div className="w-20 h-20 bg-primary/5 rounded-full flex items-center justify-center mb-6">
                        <span className="material-symbols-outlined text-4xl text-primary">
                          {uploadMutation.isPending ? 'refresh' : 'upload_file'}
                        </span>
                      </div>
                      <h3 className="text-2xl font-bold mb-2">
                         {uploadMutation.isPending ? 'Uploading to API...' : 'Drop contracts here or browse'}
                      </h3>
                      <p className="text-secondary mb-8">Support for PDF, DOCX, and TXT files</p>
                      <button className="px-6 py-2.5 border-2 border-primary text-primary font-bold rounded-full hover:bg-primary hover:text-on-primary transition-all">
                        Select Files
                      </button>
                    </div>
                  </div>

                  {/* Queue Table */}
                  <div className="bg-surface-container-lowest rounded-lg shadow-2xl shadow-slate-900/5 overflow-hidden">
                    <div className="px-8 py-6 border-b border-surface-container-low flex justify-between items-center">
                      <h3 className="font-bold text-xl">Upload Queue & History</h3>
                      <div className="flex items-center gap-2">
                        {activeProcessing > 0 && <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>}
                        <span className="text-xs font-bold uppercase tracking-widest text-secondary">{activeProcessing} Files Processing</span>
                      </div>
                    </div>
                    
                    <table className="w-full text-left">
                      <thead className="bg-surface-container-low text-[10px] font-label uppercase tracking-widest text-secondary">
                        <tr>
                          <th className="px-8 py-4">File Name</th>
                          <th className="px-8 py-4">Status</th>
                          <th className="px-8 py-4">Progress</th>
                          <th className="px-8 py-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-surface-container-low">
                        {queueToDisplay.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="px-8 py-12 text-center text-secondary">No contracts in vault. Please upload above.</td>
                          </tr>
                        ) : (
                          queueToDisplay.map((contract) => (
                            <ProcessingTableRow 
                              key={contract.id} 
                              contract={contract} 
                              isNewUpload={newUploadIds.includes(contract.id)} 
                            />
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Right Column (Insights) */}
                <div className="lg:col-span-1 space-y-8">
                  <div className="bg-surface-container-lowest p-8 rounded-lg shadow-sm border border-outline-variant/20">
                    <h4 className="text-[10px] uppercase tracking-[0.2em] font-bold text-secondary mb-6">Backend Capabilities</h4>
                    <div className="space-y-6">
                      <div className="flex gap-4">
                        <div className="flex-shrink-0 w-1 h-12 bg-primary rounded-full"></div>
                        <div>
                          <p className="text-sm font-bold text-on-surface">Vectorization Enabled</p>
                          <p className="text-xs text-secondary mt-1">Files uploaded are instantly pushed to the `/upload` API endpoint.</p>
                        </div>
                      </div>
                      <div className="flex gap-4">
                        <div className="flex-shrink-0 w-1 h-12 bg-tertiary rounded-full"></div>
                        <div>
                          <p className="text-sm font-bold text-on-surface">Data Polling Live</p>
                          <p className="text-xs text-secondary mt-1">Tanstack Query gracefully queries `/contracts/:id/status` mapping logic to visual progress bars.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}

          {activeView === 'vault' && <ContractsView contracts={contracts} />}
          {activeView === 'compare' && <CompareView contracts={contracts} />}

        </div>
      </main>
    </div>
  );
}

export default App;
