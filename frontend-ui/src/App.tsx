import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchContracts,
  uploadContract,
  fetchContractStatus,
  clearSession,
  type Contract,
  type UploadResponse,
  type AuthUser,
} from './api';
import { AnalyzeView } from './components/AnalyzeView';
import { ContractsView } from './components/ContractsView';
import { CompareView } from './components/CompareView';
import { LandingPage } from './components/LandingPage';

/* ── Processing Row (polls /status) ─────────────────────────── */

const ProcessingTableRow = ({
  contract,
  isNewUpload,
}: {
  contract: Contract;
  isNewUpload?: boolean;
}) => {
  const isProcessing = ['queued', 'parsing', 'indexing', 'processing'].includes(contract.status);

  const { data: liveStatus } = useQuery({
    queryKey: ['contractStatus', contract.id],
    queryFn: () => fetchContractStatus(contract.id),
    refetchInterval: isProcessing ? 2000 : false,
    initialData: { status: contract.status },
  });

  const currentStatus = liveStatus?.status || contract.status;
  const isDone = currentStatus === 'ready';
  const isFailed = currentStatus === 'failed';

  return (
    <tr className="table-row">
      <td className="px-5 py-4">
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${contract.filename.endsWith('.pdf') ? 'bg-red-500/10' : 'bg-blue-500/10'}`}>
            <span className={`material-symbols-outlined text-sm ${contract.filename.endsWith('.pdf') ? 'text-red-400' : 'text-blue-400'}`}>
              {contract.filename.endsWith('.pdf') ? 'picture_as_pdf' : 'description'}
            </span>
          </div>
          <div>
            <span className="font-semibold text-[var(--text-primary)] text-sm">{contract.filename}</span>
            {isNewUpload && (
              <span className="ml-2 px-1.5 py-0.5 text-[9px] font-bold rounded bg-emerald-500/15 text-emerald-400">NEW</span>
            )}
            <p className="text-[11px] text-[var(--text-muted)] mt-0.5 font-mono">{contract.id.slice(0, 12)}…</p>
          </div>
        </div>
      </td>
      <td className="px-5 py-4">
        {isDone && <span className="badge badge-ready">READY</span>}
        {isFailed && <span className="badge badge-failed">FAILED</span>}
        {!isDone && !isFailed && <span className="badge badge-processing">{currentStatus.toUpperCase()}</span>}
      </td>
      <td className="px-5 py-4">
        {contract.uploadedAt
          ? (
            <div>
              <span className="text-xs text-[var(--text-primary)] font-medium">
                {new Date(contract.uploadedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              </span>
              <span className="text-[10px] text-[var(--text-muted)] ml-1.5">
                {new Date(contract.uploadedAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}
              </span>
            </div>
          )
          : <span className="text-xs text-[var(--text-muted)]">—</span>}
      </td>
    </tr>
  );
};

/* ── Main App ───────────────────────────────────────────────── */

function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [activeView, setActiveView] = useState<'dashboard' | 'analyze' | 'vault' | 'compare'>('dashboard');
  const [newUploadIds, setNewUploadIds] = useState<string[]>([]);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Auth gate ────────────────────────────────────────────────
  if (!user) {
    return <LandingPage onAuth={(u) => setUser(u)} />;
  }

  // ── Authenticated app below ─────────────────────────────────

  return <AuthenticatedApp
    user={user}
    onSignOut={() => setUser(null)}
    activeView={activeView}
    setActiveView={setActiveView}
    newUploadIds={newUploadIds}
    setNewUploadIds={setNewUploadIds}
    queryClient={queryClient}
    fileInputRef={fileInputRef}
  />;
}

/* Extracted to a separate component so hooks are always called */
function AuthenticatedApp({
  user,
  onSignOut,
  activeView,
  setActiveView,
  newUploadIds,
  setNewUploadIds,
  queryClient,
  fileInputRef,
}: {
  user: AuthUser;
  onSignOut: () => void;
  activeView: 'dashboard' | 'analyze' | 'vault' | 'compare';
  setActiveView: (v: 'dashboard' | 'analyze' | 'vault' | 'compare') => void;
  newUploadIds: string[];
  setNewUploadIds: React.Dispatch<React.SetStateAction<string[]>>;
  queryClient: ReturnType<typeof useQueryClient>;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const { data: contracts = [], isLoading: isContractsLoading } = useQuery({
    queryKey: ['contracts'],
    queryFn: fetchContracts,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadContract,
    onSuccess: (data: UploadResponse) => {
      setNewUploadIds((prev) => [data.contract_id, ...prev]);
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
      setActiveView('vault');
    },
  });

  const clearMutation = useMutation({
    mutationFn: clearSession,
    onSuccess: () => {
      setNewUploadIds([]);
      setActiveView('dashboard');
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) uploadMutation.mutate(e.target.files[0]);
  };

  const activeProcessing = contracts.filter((c) =>
    ['queued', 'parsing', 'indexing', 'processing'].includes(c.status)
  ).length;
  const completed = contracts.filter((c) => c.status === 'ready').length;
  const failed = contracts.filter((c) => c.status === 'failed' || c.status === 'error').length;

  const recentContracts = [...contracts]
    .sort((a, b) => {
      if (newUploadIds.includes(a.id) && !newUploadIds.includes(b.id)) return -1;
      if (!newUploadIds.includes(a.id) && newUploadIds.includes(b.id)) return 1;
      return 0;
    })
    .slice(0, 5);

  const navItems = [
    { key: 'dashboard' as const, icon: 'home', label: 'Overview' },
    { key: 'analyze' as const, icon: 'bolt', label: 'New Scan' },
    { key: 'vault' as const, icon: 'folder_open', label: 'History' },
    { key: 'compare' as const, icon: 'compare_arrows', label: 'Compare' },
  ];

  const userInitial = user.display_name?.charAt(0)?.toUpperCase() || 'U';

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg-root)' }}>
      {/* ── Sidebar ──────────────────────────────────────────── */}
      <aside className="sidebar fixed top-0 left-0 bottom-0 w-[250px] flex flex-col z-50">
        {/* Logo */}
        <div className="px-5 py-6 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/15 flex items-center justify-center animate-glow">
            <span className="material-symbols-outlined text-emerald-400 text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>shield</span>
          </div>
          <span className="text-emerald-400 font-bold text-base tracking-tight">CONTRACTGUARD</span>
        </div>

        {/* Nav Items */}
        <nav className="px-3 mt-2 space-y-1 flex-1">
          {navItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setActiveView(item.key)}
              className={`sidebar-item w-full text-left ${activeView === item.key ? 'active' : ''}`}
            >
              <span className="material-symbols-outlined text-lg" style={{ fontVariationSettings: activeView === item.key ? "'FILL' 1" : "'FILL' 0" }}>
                {item.icon}
              </span>
              {item.label}
              {item.key === 'vault' && contracts.length > 0 && (
                <span className="ml-auto text-[10px] font-bold bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded-full">
                  {contracts.length}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Bottom Actions */}
        <div className="px-3 pb-4 space-y-2">
          <button
            onClick={() => clearMutation.mutate()}
            className="sidebar-item w-full text-left text-red-400/60 hover:text-red-400 hover:bg-red-500/10"
          >
            <span className="material-symbols-outlined text-lg">delete_sweep</span>
            Clear Vault
          </button>
          <button
            onClick={() => setActiveView('analyze')}
            className="btn-primary w-full flex items-center justify-center gap-2 text-sm"
          >
            <span className="material-symbols-outlined text-base">add</span> New Upload
          </button>
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept=".pdf,.docx,.txt"
            onChange={handleFileSelect}
          />
        </div>

        {/* User Profile */}
        <div className="px-4 py-4 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center text-sm font-bold text-emerald-400">
              {userInitial}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-[var(--text-primary)] truncate">{user.display_name}</p>
              <p className="text-[10px] text-[var(--text-muted)] truncate">
                {user.is_guest ? 'Guest Session' : user.email}
              </p>
            </div>
            <button
              onClick={onSignOut}
              className="text-[var(--text-muted)] hover:text-red-400 transition-colors"
              title="Sign out"
            >
              <span className="material-symbols-outlined text-base">logout</span>
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main Content ─────────────────────────────────────── */}
      <main className="ml-[250px] flex-1 min-h-screen">
        {/* Top Bar */}
        <header className="sticky top-0 z-40 px-8 h-14 flex items-center justify-between" style={{ background: 'var(--bg-root)', borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center gap-3">
            <div className="input-dark flex items-center gap-2 w-72">
              <span className="material-symbols-outlined text-[var(--text-muted)] text-sm">search</span>
              <input className="bg-transparent border-none outline-none text-sm w-full text-[var(--text-primary)] placeholder:text-[var(--text-muted)]" placeholder="Search contracts…" type="text" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isContractsLoading ? 'bg-amber-400 animate-pulse' : 'bg-emerald-500'}`} />
            <span className="text-xs text-[var(--text-muted)] font-medium">
              {isContractsLoading ? 'Syncing…' : 'Connected'}
            </span>
          </div>
        </header>

        <div className="max-w-6xl mx-auto px-8 py-8">
          {/* ── Dashboard Overview ─────────────────────────── */}
          {activeView === 'dashboard' && (
            <div className="animate-fade-in-up">
              {/* Welcome Header */}
              <div className="mb-8">
                <h1 className="text-3xl font-bold text-[var(--text-primary)]">Welcome back, {user.display_name}</h1>
                <p className="text-[var(--text-secondary)] mt-1">Here is an overview of your contract analysis usage and recent activity.</p>
              </div>

              {/* Stats Row */}
              <div className="grid grid-cols-3 gap-5 mb-8 animate-fade-in-up-delay-1">
                {/* Scans Used */}
                <div className="card-accent p-6">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[11px] font-bold uppercase tracking-widest text-[var(--text-muted)]">Contracts Analyzed</span>
                    <span className="material-symbols-outlined text-emerald-400 text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>query_stats</span>
                  </div>
                  <div className="flex items-end gap-1">
                    <span className="text-4xl font-black text-[var(--text-primary)]">{completed}</span>
                    <span className="text-lg text-[var(--text-muted)] mb-1">/ ∞</span>
                  </div>
                  <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
                    <div className="h-full rounded-full bg-emerald-500 transition-all duration-1000" style={{ width: `${Math.min(completed * 5, 100)}%` }} />
                  </div>
                </div>

                {/* Current Plan */}
                <div className="card p-6">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[11px] font-bold uppercase tracking-widest text-[var(--text-muted)]">Current Plan</span>
                    <span className="material-symbols-outlined text-emerald-400 text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>diamond</span>
                  </div>
                  <p className="text-2xl font-black text-emerald-400 mb-1">Pro Tier</p>
                  <p className="text-xs text-[var(--text-muted)]">Unlimited AI analysis with Gemini 2.5 Pro & Indian Law citations</p>
                </div>

                {/* CTA */}
                <div className="card-cta p-6 flex flex-col justify-between">
                  <div>
                    <h3 className="text-lg font-bold mb-1">Initiate Analysis</h3>
                    <p className="text-sm text-white/70">Upload a contract or paste text for AI-powered risk analysis</p>
                  </div>
                  <button onClick={() => setActiveView('analyze')} className="mt-4 w-full py-2.5 bg-white/20 hover:bg-white/30 rounded-lg font-bold text-sm transition-all backdrop-blur-sm">
                    Launch Scanner
                  </button>
                </div>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-4 gap-4 mb-8 animate-fade-in-up-delay-2">
                {[
                  { label: 'Total Contracts', value: contracts.length, icon: 'folder_zip', color: 'text-slate-400' },
                  { label: 'Processing', value: activeProcessing, icon: 'sync', color: 'text-blue-400' },
                  { label: 'Completed', value: completed, icon: 'verified', color: 'text-emerald-400' },
                  { label: 'Failed', value: failed, icon: 'report', color: 'text-red-400' },
                ].map((stat) => (
                  <div key={stat.label} className="card p-4">
                    <div className="flex items-center gap-3">
                      <span className={`material-symbols-outlined text-lg ${stat.color}`} style={{ fontVariationSettings: "'FILL' 1" }}>{stat.icon}</span>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)]">{stat.label}</p>
                        <p className="text-xl font-black text-[var(--text-primary)]">{stat.value}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Recent Scans */}
              <div className="card overflow-hidden animate-fade-in-up-delay-2">
                <div className="px-5 py-4 flex justify-between items-center" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <h3 className="font-bold text-base text-[var(--text-primary)]">Recent Scans</h3>
                  <button onClick={() => setActiveView('vault')} className="text-xs font-bold text-emerald-400 hover:text-emerald-300 transition-colors flex items-center gap-1">
                    View All History <span className="material-symbols-outlined text-sm">arrow_forward</span>
                  </button>
                </div>
                <table className="w-full text-left">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <th className="px-5 py-3 table-header">Source / File</th>
                      <th className="px-5 py-3 table-header">Status</th>
                      <th className="px-5 py-3 table-header">Scanned At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentContracts.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-5 py-12 text-center text-[var(--text-muted)] text-sm">
                          No contracts uploaded yet. Go to <button onClick={() => setActiveView('analyze')} className="text-emerald-400 font-bold hover:underline">New Scan</button> to get started.
                        </td>
                      </tr>
                    ) : (
                      recentContracts.map((contract) => (
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
          )}

          {/* ── Dedicated Views ────────────────────────────── */}
          {activeView === 'analyze' && <AnalyzeView />}
          {activeView === 'vault' && <ContractsView contracts={contracts} />}
          {activeView === 'compare' && <CompareView contracts={contracts} />}
        </div>
      </main>
    </div>
  );
}

export default App;

