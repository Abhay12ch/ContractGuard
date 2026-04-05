import { useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  uploadContract,
  ingestText,
  fetchSummary,
  fetchRisks,
  fetchMetadata,
  fetchVendorVerification,
  askQuestion,
  type UploadResponse,
  type RiskItem,
  type MetadataField,
  type VendorVerificationCheck,
} from '../api';
import { MarkdownText } from './MarkdownText';

/* ── Skeleton ──────────────────────────────────────────────── */
const Skeleton = ({ className = '' }: { className?: string }) => (
  <div className={`skeleton ${className}`} />
);

/* ── Severity Badge ────────────────────────────────────────── */
const SeverityBadge = ({ severity }: { severity: string }) => {
  const s = severity.toLowerCase();
  let cls = 'severity-low';
  if (s === 'high') cls = 'severity-high';
  else if (s === 'medium') cls = 'severity-medium';
  return <span className={`${cls} px-2.5 py-0.5 rounded-md text-xs font-bold uppercase`}>{severity}</span>;
};

/* ── Risk Gauge ────────────────────────────────────────────── */
const RiskGauge = ({ score }: { score: number }) => {
  const r = 46, circumference = 2 * Math.PI * r;
  const offset = circumference - (score / 100) * circumference;
  let color = '#ef4444';
  if (score >= 80) color = '#10b981';
  else if (score >= 60) color = '#f59e0b';
  else if (score >= 40) color = '#f97316';
  return (
    <div className="relative w-28 h-28 mx-auto">
      <svg width="112" height="112" viewBox="0 0 112 112">
        <circle cx="56" cy="56" r={r} fill="none" stroke="var(--border-subtle)" strokeWidth="7" />
        <circle cx="56" cy="56" r={r} fill="none" stroke={color} strokeWidth="7"
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
          className="transition-all duration-1000" style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <p className="text-2xl font-black" style={{ color }}>{score}</p>
        <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Safety</p>
      </div>
    </div>
  );
};

/* ── Confidence Bar ────────────────────────────────────────── */
const ConfidenceBar = ({ confidence }: { confidence: number }) => {
  let color = 'bg-red-500';
  if (confidence >= 70) color = 'bg-emerald-500';
  else if (confidence >= 40) color = 'bg-amber-500';
  return (
    <div className="flex items-center gap-2">
      <div className="confidence-bar flex-1"><div className={`confidence-bar-fill ${color}`} style={{ width: `${confidence}%` }} /></div>
      <span className="text-xs font-bold text-[var(--text-muted)] w-8 text-right">{confidence}%</span>
    </div>
  );
};

/* ── Field Labels ──────────────────────────────────────────── */
const FIELD_LABELS: Record<string, { label: string; icon: string }> = {
  customer_name: { label: 'Customer Name', icon: 'person' },
  vendor_name: { label: 'Vendor Name', icon: 'storefront' },
  contract_type: { label: 'Contract Type', icon: 'category' },
  governing_law: { label: 'Governing Law', icon: 'gavel' },
  effective_date: { label: 'Effective Date', icon: 'event' },
  expiration_date: { label: 'Expiration Date', icon: 'event_busy' },
  payment_terms: { label: 'Payment Terms', icon: 'payments' },
  billing_cycle: { label: 'Billing Cycle', icon: 'schedule' },
  total_value: { label: 'Total Value', icon: 'attach_money' },
  renewal_terms: { label: 'Renewal Terms', icon: 'autorenew' },
};

/* ── Results Panel ─────────────────────────────────────────── */
const ResultsPanel = ({ contractId, filename }: { contractId: string; filename: string }) => {
  const [activeTab, setActiveTab] = useState<'summary' | 'risks' | 'metadata' | 'vendor' | 'chat'>('summary');
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState<{ question: string; answer: string; chunks?: number }[]>([]);
  const [sessionId, setSessionId] = useState('');

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['summary', contractId],
    queryFn: () => fetchSummary(contractId),
    staleTime: 300000,
    retry: 3,
    retryDelay: 2000,
  });

  const { data: risks, isLoading: risksLoading } = useQuery({
    queryKey: ['risks', contractId],
    queryFn: () => fetchRisks(contractId),
    staleTime: 300000,
    retry: 3,
    retryDelay: 2000,
  });

  const { data: metadata, isLoading: metadataLoading } = useQuery({
    queryKey: ['metadata', contractId],
    queryFn: () => fetchMetadata(contractId),
    staleTime: 300000,
    retry: 3,
    retryDelay: 2000,
  });

  const { data: vendorData, isLoading: vendorLoading } = useQuery({
    queryKey: ['vendor', contractId],
    queryFn: () => fetchVendorVerification(contractId),
    staleTime: 300000,
    retry: 2,
    retryDelay: 2000,
  });

  const askMutation = useMutation({
    mutationFn: (question: string) => askQuestion(contractId, question, sessionId),
    onSuccess: (data) => {
      setChatHistory((prev) => [...prev, { question: data.question, answer: data.answer, chunks: data.retrieved_chunks_count }]);
      setSessionId(data.session_id || sessionId);
      setChatInput('');
    },
  });

  // Show processing screen while core data is still loading
  const coreLoading = summaryLoading || risksLoading || metadataLoading;

  const metadataFields = metadata?.metadata || {};
  const extractedCount = Object.values(metadataFields).filter((f: MetadataField) => f.value && f.value.trim()).length;
  const totalFields = Object.keys(metadataFields).length || 10;
  const avgConfidence = totalFields > 0
    ? Math.round(Object.values(metadataFields).reduce((s: number, f: MetadataField) => s + f.confidence, 0) / totalFields)
    : 0;

  const tabs = [
    { key: 'summary' as const, icon: 'summarize', label: 'Summary' },
    { key: 'risks' as const, icon: 'shield', label: 'Risks' },
    { key: 'metadata' as const, icon: 'database', label: 'Metadata' },
    { key: 'vendor' as const, icon: 'verified_user', label: 'Vendor Trust' },
    { key: 'chat' as const, icon: 'forum', label: 'Ask AI' },
  ];

  const quickQuestions = [
    'What are the termination conditions?',
    'Are there any auto-renewal clauses?',
    'What liability limits are defined?',
  ];

  /* ── Processing Screen ── */
  if (coreLoading) {
    const steps = [
      { label: 'Parsing document', icon: 'description', done: !summaryLoading },
      { label: 'Running risk analysis', icon: 'shield', done: !risksLoading },
      { label: 'Extracting metadata', icon: 'database', done: !metadataLoading },
      { label: 'Preparing Q&A engine', icon: 'forum', done: false },
    ];

    return (
      <div className="animate-fade-in-up">
        <div className="card p-10 text-center">
          {/* Animated spinner */}
          <div className="w-20 h-20 mx-auto mb-6 relative">
            <div className="absolute inset-0 rounded-full" style={{ border: '3px solid var(--border-subtle)' }} />
            <div className="absolute inset-0 rounded-full animate-spin" style={{ border: '3px solid transparent', borderTopColor: '#10b981', borderRightColor: '#10b981' }} />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="material-symbols-outlined text-emerald-400 text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>psychology</span>
            </div>
          </div>

          <h2 className="text-xl font-bold text-[var(--text-primary)] mb-1">Analyzing Contract</h2>
          <p className="text-sm text-[var(--text-muted)] mb-8">{filename}</p>

          {/* Progress steps */}
          <div className="max-w-sm mx-auto text-left space-y-4">
            {steps.map((step, idx) => (
              <div key={idx} className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-all duration-500 ${
                  step.done
                    ? 'bg-emerald-500/15'
                    : idx === steps.findIndex(s => !s.done)
                      ? 'bg-emerald-500/10'
                      : ''
                }`} style={!step.done && idx !== steps.findIndex(s => !s.done) ? { background: 'var(--bg-elevated)' } : {}}>
                  {step.done ? (
                    <span className="material-symbols-outlined text-emerald-400 text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
                  ) : idx === steps.findIndex(s => !s.done) ? (
                    <span className="material-symbols-outlined text-emerald-400 text-sm animate-pulse">{step.icon}</span>
                  ) : (
                    <span className="material-symbols-outlined text-[var(--text-muted)] text-sm opacity-40">{step.icon}</span>
                  )}
                </div>
                <div className="flex-1">
                  <p className={`text-sm font-semibold transition-colors ${
                    step.done ? 'text-emerald-400' : idx === steps.findIndex(s => !s.done) ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] opacity-50'
                  }`}>
                    {step.label}
                    {idx === steps.findIndex(s => !s.done) && <span className="ml-1 text-xs text-[var(--text-muted)]">…</span>}
                  </p>
                </div>
                {step.done && <span className="text-[9px] font-bold text-emerald-400/60 uppercase">Done</span>}
              </div>
            ))}
          </div>

          <p className="text-xs text-[var(--text-muted)] mt-8">This usually takes 10-30 seconds depending on document size.</p>
        </div>
      </div>
    );
  }

  /* ── Results (shown only after all data is ready) ── */
  return (
    <div className="animate-fade-in-up space-y-6">
      {/* Results Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-emerald-500/15 flex items-center justify-center">
          <span className="material-symbols-outlined text-emerald-400" style={{ fontVariationSettings: "'FILL' 1" }}>task_alt</span>
        </div>
        <div>
          <h2 className="text-lg font-bold text-[var(--text-primary)]">Analysis Complete</h2>
          <p className="text-xs text-[var(--text-muted)]">{filename}</p>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 rounded-xl p-1" style={{ background: 'var(--bg-card)' }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-sm font-bold transition-all ${
              activeTab === tab.key ? 'text-emerald-400' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
            }`}
            style={activeTab === tab.key ? { background: 'var(--accent-glow)', border: '1px solid rgba(16,185,129,0.2)' } : {}}
          >
            <span className="material-symbols-outlined text-base" style={activeTab === tab.key ? { fontVariationSettings: "'FILL' 1" } : undefined}>
              {tab.icon}
            </span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Summary Tab ─────────────────────────── */}
      {activeTab === 'summary' && (
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-emerald-400" style={{ fontVariationSettings: "'FILL' 1" }}>summarize</span>
            <h3 className="font-bold text-lg text-[var(--text-primary)]">AI-Generated Summary</h3>
          </div>
          {summaryLoading ? (
            <div className="space-y-3"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-4/6" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-3/6" /></div>
          ) : (
            <MarkdownText text={summary || 'No summary available.'} />
          )}
        </div>
      )}

      {/* ── Risks Tab ───────────────────────────── */}
      {activeTab === 'risks' && (
        <div className="space-y-5">
          {risksLoading ? (
            <div className="space-y-4"><Skeleton className="h-36 w-full" /><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div>
          ) : risks ? (
            <>
              {/* Score Panel */}
              <div className="card p-6">
                <div className="grid grid-cols-3 gap-6 items-center">
                  <RiskGauge score={risks.safety_score} />
                  <div className="text-center">
                    <span className={`px-4 py-1.5 rounded-lg text-sm font-bold inline-flex items-center gap-1.5 ${
                      risks.risk_level.toLowerCase().includes('low') ? 'severity-low'
                      : risks.risk_level.toLowerCase().includes('moderate') ? 'severity-medium' : 'severity-high'
                    }`}>
                      <span className="material-symbols-outlined text-base">
                        {risks.risk_level.toLowerCase().includes('low') ? 'verified_user' : 'gpp_bad'}
                      </span>
                      {risks.risk_level}
                    </span>
                    <p className="text-2xl font-black text-[var(--text-primary)] mt-3">{risks.detected_clause_count}</p>
                    <p className="text-xs text-[var(--text-muted)] font-bold uppercase tracking-widest">Risky Clauses</p>
                  </div>
                  <div className="space-y-3">
                    <div className="card-elevated rounded-lg p-3">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400/60 mb-0.5 flex items-center gap-1">
                        <span className="material-symbols-outlined text-[10px]">verified_user</span> Safety Score
                      </p>
                      <p className="text-lg font-black text-emerald-400">{risks.safety_score}<span className="text-sm text-[var(--text-muted)]">/100</span></p>
                      <p className="text-[9px] text-[var(--text-muted)] mt-0.5">Higher = Safer</p>
                    </div>
                    <div className="card-elevated rounded-lg p-3">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-red-400/60 mb-0.5 flex items-center gap-1">
                        <span className="material-symbols-outlined text-[10px]">warning</span> Risk Score
                      </p>
                      <p className="text-lg font-black text-red-400">{risks.risk_score}<span className="text-sm text-[var(--text-muted)]">/100</span></p>
                      <p className="text-[9px] text-[var(--text-muted)] mt-0.5">Σ(impact × severity weight)</p>
                    </div>
                  </div>
                </div>

                {/* Severity Distribution Bar */}
                {risks.risks.length > 0 && (() => {
                  const high = risks.risks.filter((r: RiskItem) => r.severity === 'High').length;
                  const med = risks.risks.filter((r: RiskItem) => r.severity === 'Medium').length;
                  const low = risks.risks.filter((r: RiskItem) => r.severity === 'Low').length;
                  const total = risks.risks.length;
                  return (
                    <div className="mt-5 pt-5" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <div className="flex items-center justify-between mb-2">
                        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)]">Severity Distribution</p>
                        <div className="flex items-center gap-4">
                          {high > 0 && <span className="flex items-center gap-1.5 text-[10px] font-bold"><span className="w-2 h-2 rounded-full bg-red-500" /><span className="text-[var(--text-muted)]">{high} High</span></span>}
                          {med > 0 && <span className="flex items-center gap-1.5 text-[10px] font-bold"><span className="w-2 h-2 rounded-full bg-amber-500" /><span className="text-[var(--text-muted)]">{med} Medium</span></span>}
                          {low > 0 && <span className="flex items-center gap-1.5 text-[10px] font-bold"><span className="w-2 h-2 rounded-full bg-blue-400" /><span className="text-[var(--text-muted)]">{low} Low</span></span>}
                        </div>
                      </div>
                      <div className="flex h-2 rounded-full overflow-hidden gap-0.5">
                        {high > 0 && <div className="bg-red-500 rounded-full transition-all" style={{ width: `${(high / total) * 100}%` }} />}
                        {med > 0 && <div className="bg-amber-500 rounded-full transition-all" style={{ width: `${(med / total) * 100}%` }} />}
                        {low > 0 && <div className="bg-blue-400 rounded-full transition-all" style={{ width: `${(low / total) * 100}%` }} />}
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* Risk Cards */}
              {risks.risks.length === 0 ? (
                <div className="card-accent p-6 text-center">
                  <span className="material-symbols-outlined text-3xl text-emerald-400 mb-2" style={{ fontVariationSettings: "'FILL' 1" }}>verified_user</span>
                  <p className="font-bold text-emerald-400">No risky clauses detected</p>
                  <p className="text-sm text-[var(--text-muted)] mt-1">This contract appears safe.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <h4 className="font-bold text-xs text-[var(--text-muted)] uppercase tracking-widest">
                    Detected Clauses ({risks.risks.length})
                  </h4>
                  {risks.risks.map((risk: RiskItem, idx: number) => {
                    const borderColor = risk.severity === 'High' ? '#ef4444' : risk.severity === 'Medium' ? '#f59e0b' : '#60a5fa';
                    return (
                      <div key={idx} className="card overflow-hidden hover:border-[var(--border-default)] transition-all"
                        style={{ borderLeft: `3px solid ${borderColor}` }}>
                        <div className="p-5">
                          {/* Header */}
                          <div className="flex items-start justify-between gap-4 mb-3">
                            <div className="flex items-center gap-2.5">
                              <span className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold" style={{ background: `${borderColor}15`, color: borderColor }}>{idx + 1}</span>
                              <h5 className="font-bold text-[var(--text-primary)] text-sm">{risk.title}</h5>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              <SeverityBadge severity={risk.severity} />
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-md" style={{ background: `${borderColor}12`, color: borderColor }}>
                                Impact: {risk.impact}
                              </span>
                            </div>
                          </div>

                          {/* Explanation */}
                          {risk.explanation && (
                            <div className="mb-3">
                              <MarkdownText text={risk.explanation} className="text-sm" />
                            </div>
                          )}

                          {/* Evidence & Legal Source */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                            {risk.evidence && (
                              <div className="rounded-lg px-3.5 py-2.5" style={{ background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.12)' }}>
                                <p className="text-[9px] font-bold text-amber-500/70 uppercase tracking-widest mb-1 flex items-center gap-1">
                                  <span className="material-symbols-outlined text-[10px]">format_quote</span> Evidence
                                </p>
                                <p className="text-xs text-amber-400/80 italic leading-relaxed">"{risk.evidence}"</p>
                              </div>
                            )}
                            {risk.source && (
                              <div className="rounded-lg px-3.5 py-2.5" style={{ background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.12)' }}>
                                <p className="text-[9px] font-bold text-blue-400/70 uppercase tracking-widest mb-1 flex items-center gap-1">
                                  <span className="material-symbols-outlined text-[10px]">menu_book</span> Legal Source
                                </p>
                                <p className="text-xs text-blue-300/80 leading-relaxed">{risk.source}</p>
                                {risk.source_url && (
                                  <a href={risk.source_url} target="_blank" rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-bold text-blue-400 hover:text-blue-300 transition-colors">
                                    <span className="material-symbols-outlined text-xs">open_in_new</span> View Legal Text →
                                  </a>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          ) : <p className="text-[var(--text-muted)] text-center py-8">Could not load risk analysis.</p>}
        </div>
      )}

      {/* ── Metadata Tab ────────────────────────── */}
      {activeTab === 'metadata' && (
        <div className="space-y-5">
          {metadataLoading ? (
            <div className="space-y-4"><Skeleton className="h-20 w-full" /><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
          ) : metadata ? (
            <>
              {/* KPI Row */}
              <div className="grid grid-cols-3 gap-4">
                <div className="card p-5 flex items-center gap-4">
                  <div className="relative w-12 h-12 flex-shrink-0">
                    <svg width="48" height="48" viewBox="0 0 48 48">
                      <circle cx="24" cy="24" r="19" fill="none" stroke="var(--border-subtle)" strokeWidth="4" />
                      <circle cx="24" cy="24" r="19" fill="none" stroke="#10b981" strokeWidth="4"
                        strokeDasharray={2 * Math.PI * 19} strokeDashoffset={2 * Math.PI * 19 * (1 - extractedCount / Math.max(totalFields, 1))}
                        strokeLinecap="round" style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }} />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="text-xs font-black text-emerald-400">{extractedCount}</span>
                    </div>
                  </div>
                  <div>
                    <p className="text-lg font-black text-[var(--text-primary)]">{extractedCount}<span className="text-sm text-[var(--text-muted)]">/{totalFields}</span></p>
                    <p className="text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)]">Fields Extracted</p>
                  </div>
                </div>
                <div className="card p-5 flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(59,130,246,0.1)' }}>
                    <span className="material-symbols-outlined text-blue-400 text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>speed</span>
                  </div>
                  <div>
                    <p className="text-lg font-black text-blue-400">{avgConfidence}<span className="text-sm text-[var(--text-muted)]">%</span></p>
                    <p className="text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)]">Avg Confidence</p>
                  </div>
                </div>
                <div className="card p-5 flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: totalFields - extractedCount > 0 ? 'rgba(251,191,36,0.1)' : 'rgba(16,185,129,0.1)' }}>
                    <span className="material-symbols-outlined text-xl" style={{ fontVariationSettings: "'FILL' 1", color: totalFields - extractedCount > 0 ? '#fbbf24' : '#10b981' }}>
                      {totalFields - extractedCount > 0 ? 'help' : 'check_circle'}
                    </span>
                  </div>
                  <div>
                    <p className="text-lg font-black" style={{ color: totalFields - extractedCount > 0 ? '#fbbf24' : '#10b981' }}>{totalFields - extractedCount}</p>
                    <p className="text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)]">Data Gaps</p>
                  </div>
                </div>
              </div>

              {/* Grouped Fields */}
              {(() => {
                const groups: Record<string, string[]> = {};
                Object.keys(metadataFields).forEach((key) => {
                  const info = FIELD_LABELS[key];
                  const groupName = info && 'group' in info ? (info as any).group || 'Other' : 'Other';
                  if (!groups[groupName]) groups[groupName] = [];
                  groups[groupName].push(key);
                });
                const groupIcons: Record<string, string> = { Parties: 'group', 'Contract Info': 'description', Dates: 'calendar_month', Financial: 'account_balance', Terms: 'handshake', Other: 'more_horiz' };

                return Object.entries(groups).map(([groupName, keys]) => (
                  <div key={groupName} className="card overflow-hidden">
                    <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <span className="material-symbols-outlined text-emerald-400 text-base" style={{ fontVariationSettings: "'FILL' 1" }}>
                        {groupIcons[groupName] || 'folder'}
                      </span>
                      <h3 className="font-bold text-sm text-[var(--text-primary)]">{groupName}</h3>
                      <span className="text-[10px] font-bold text-[var(--text-muted)] ml-auto">{keys.length} fields</span>
                    </div>
                    {keys.map((key, ki) => {
                      const f = metadataFields[key] as MetadataField;
                      const info = FIELD_LABELS[key] || { label: key, icon: 'info' };
                      const hasValue = !!(f.value && f.value.trim());
                      return (
                        <div key={key} className="px-5 py-3.5 hover:bg-[var(--bg-card-hover)] transition-colors"
                          style={ki < keys.length - 1 ? { borderBottom: '1px solid var(--border-subtle)' } : {}}>
                          <div className="flex items-center justify-between gap-4">
                            <div className="flex items-center gap-3 flex-1 min-w-0">
                              <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${hasValue ? 'bg-emerald-500/10' : ''}`}
                                style={!hasValue ? { background: 'var(--bg-elevated)' } : {}}>
                                <span className={`material-symbols-outlined text-sm ${hasValue ? 'text-emerald-400' : 'text-[var(--text-muted)] opacity-40'}`}
                                  style={hasValue ? { fontVariationSettings: "'FILL' 1" } : undefined}>
                                  {info.icon}
                                </span>
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">{info.label}</p>
                                <p className={`text-sm font-semibold mt-0.5 ${hasValue ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] italic text-xs'}`}>
                                  {hasValue ? f.value : '— Not found in contract'}
                                </p>
                              </div>
                            </div>
                            <div className="w-36 flex-shrink-0"><ConfidenceBar confidence={f.confidence} /></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ));
              })()}
            </>
          ) : <p className="text-[var(--text-muted)] text-center py-8">Could not load metadata.</p>}
        </div>
      )}

      {/* ── Chat Tab ─────────────────────────────── */}
      {activeTab === 'chat' && (
        <div className="space-y-4">
          {/* Quick Questions */}
          <div className="flex flex-wrap gap-2">
            {quickQuestions.map((q) => (
              <button key={q} onClick={() => { setChatInput(q); askMutation.mutate(q); }} disabled={askMutation.isPending}
                className="px-3 py-1.5 rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
                style={{ background: 'var(--accent-glow)', color: 'var(--accent-light)', border: '1px solid rgba(16,185,129,0.2)' }}>
                {q}
              </button>
            ))}
          </div>
          {/* Chat History */}
          <div className="card min-h-[250px] max-h-[400px] overflow-y-auto p-5 space-y-3">
            {chatHistory.length === 0 && !askMutation.isPending && (
              <div className="text-center py-10">
                <span className="material-symbols-outlined text-4xl text-[var(--text-muted)] mb-2 opacity-30" style={{ fontVariationSettings: "'FILL' 1" }}>forum</span>
                <p className="text-sm text-[var(--text-secondary)]">Ask a question about this contract</p>
              </div>
            )}
            {chatHistory.map((item, idx) => (
              <div key={idx} className="space-y-2.5 animate-fade-in-up">
                <div className="flex justify-end"><div className="bg-emerald-600 text-white px-3.5 py-2 rounded-2xl rounded-tr-md max-w-[78%]"><p className="text-sm">{item.question}</p></div></div>
                <div className="flex justify-start"><div className="px-3.5 py-2.5 rounded-2xl rounded-tl-md max-w-[78%]" style={{ background: 'var(--bg-elevated)' }}>
                  <MarkdownText text={item.answer} className="text-sm" />
                  {item.chunks !== undefined && <p className="text-[9px] text-[var(--text-muted)] mt-1.5 font-bold">Based on {item.chunks} chunks</p>}
                </div></div>
              </div>
            ))}
            {askMutation.isPending && (
              <div className="flex justify-start"><div className="px-3.5 py-2.5 rounded-2xl rounded-tl-md" style={{ background: 'var(--bg-elevated)' }}>
                <div className="flex items-center gap-2"><span className="material-symbols-outlined animate-spin text-sm text-[var(--text-muted)]">refresh</span><p className="text-sm text-[var(--text-muted)]">Searching…</p></div>
              </div></div>
            )}
          </div>
          {/* Input */}
          <div className="flex gap-2">
            <input type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && chatInput.trim() && !askMutation.isPending) askMutation.mutate(chatInput.trim()); }}
              placeholder="Ask about this contract…" className="input-dark flex-1" />
            <button onClick={() => { if (chatInput.trim()) askMutation.mutate(chatInput.trim()); }}
              disabled={!chatInput.trim() || askMutation.isPending}
              className="btn-primary px-5 flex items-center gap-1.5 disabled:opacity-50">
              <span className="material-symbols-outlined text-base">send</span> Ask
            </button>
          </div>
        </div>
      )}

      {/* ── Tab: Vendor Trust ────────────────────────────── */}
      {activeTab === 'vendor' && (
        <div className="space-y-5">
          {vendorLoading ? (
            <div className="space-y-4"><Skeleton className="h-40 w-full" /><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div>
          ) : vendorData ? (
            <>
              {/* Trust Score Panel */}
              <div className="card p-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
                  {/* Trust Gauge */}
                  <div className="flex flex-col items-center">
                    <div className="relative w-28 h-28">
                      <svg width="112" height="112" viewBox="0 0 112 112">
                        <circle cx="56" cy="56" r="48" fill="none" stroke="var(--border-subtle)" strokeWidth="8" />
                        <circle cx="56" cy="56" r="48" fill="none"
                          stroke={vendorData.trust_score >= 75 ? '#10b981' : vendorData.trust_score >= 40 ? '#f59e0b' : '#ef4444'}
                          strokeWidth="8" strokeDasharray={2 * Math.PI * 48}
                          strokeDashoffset={2 * Math.PI * 48 * (1 - vendorData.trust_score / 100)}
                          strokeLinecap="round" style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%', transition: 'stroke-dashoffset 1s ease' }} />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-3xl font-black" style={{ color: vendorData.trust_score >= 75 ? '#10b981' : vendorData.trust_score >= 40 ? '#f59e0b' : '#ef4444' }}>
                          {vendorData.trust_score}
                        </span>
                        <span className="text-[9px] font-bold text-[var(--text-muted)] uppercase">Trust Score</span>
                      </div>
                    </div>
                  </div>
                  {/* Trust Level + Vendor Name */}
                  <div className="flex flex-col items-center gap-3">
                    <div className={`px-4 py-1.5 rounded-full text-xs font-black uppercase tracking-widest ${
                      vendorData.trust_level === 'Verified' ? 'bg-emerald-500/15 text-emerald-400' :
                      vendorData.trust_level === 'Caution' ? 'bg-amber-500/15 text-amber-400' :
                      'bg-red-500/15 text-red-400'
                    }`}>
                      {vendorData.trust_level === 'Verified' ? '✅' : vendorData.trust_level === 'Caution' ? '⚠️' : '🚨'} {vendorData.trust_level}
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-bold text-[var(--text-primary)]">{vendorData.vendor_name || 'Unknown Vendor'}</p>
                      <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mt-1">Vendor Entity</p>
                    </div>
                    <span className="text-[9px] font-bold px-2 py-0.5 rounded-full" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                      {vendorData.verification_mode === 'ai_assessment' ? '🤖 AI Assessment' : '🔍 Registry Lookup'}
                    </span>
                  </div>
                  {/* Registry Data */}
                  <div className="space-y-2">
                    {Object.entries(vendorData.registry_data || {}).map(([key, val]) => (
                      <div key={key} className="card-elevated rounded-lg px-3 py-2">
                        <p className="text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)]">{key.replace(/_/g, ' ')}</p>
                        <p className="text-sm font-semibold text-[var(--text-primary)] mt-0.5">{String(val) || '—'}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Verification Checks */}
              <div className="card overflow-hidden">
                <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <span className="material-symbols-outlined text-emerald-400 text-base" style={{ fontVariationSettings: "'FILL' 1" }}>checklist</span>
                  <h3 className="font-bold text-sm text-[var(--text-primary)]">Verification Checks</h3>
                  <span className="text-[10px] font-bold text-[var(--text-muted)] ml-auto">
                    {vendorData.checks.filter((c: VendorVerificationCheck) => c.passed).length}/{vendorData.checks.length} passed
                  </span>
                </div>
                {vendorData.checks.map((check: VendorVerificationCheck, idx: number) => (
                  <div key={idx} className="px-5 py-3.5 hover:bg-[var(--bg-card-hover)] transition-colors"
                    style={idx < vendorData.checks.length - 1 ? { borderBottom: '1px solid var(--border-subtle)' } : {}}>
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        check.passed ? 'bg-emerald-500/10' : 'bg-red-500/10'
                      }`}>
                        <span className={`material-symbols-outlined text-sm ${check.passed ? 'text-emerald-400' : 'text-red-400'}`}
                          style={{ fontVariationSettings: "'FILL' 1" }}>
                          {check.passed ? 'check_circle' : 'cancel'}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-bold text-[var(--text-primary)]">{check.check}</p>
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                            check.passed ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
                          }`}>+{check.points}/{check.max_points}</span>
                        </div>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5 leading-relaxed">{check.detail}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Red Flags */}
              {vendorData.red_flags && vendorData.red_flags.length > 0 && (
                <div className="space-y-2">
                  <h4 className="font-bold text-xs text-[var(--text-muted)] uppercase tracking-widest">Red Flags ({vendorData.red_flags.length})</h4>
                  {vendorData.red_flags.map((flag: string, idx: number) => (
                    <div key={idx} className="rounded-lg px-4 py-3" style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.12)' }}>
                      <div className="flex items-start gap-2">
                        <span className="material-symbols-outlined text-red-400 text-sm mt-0.5" style={{ fontVariationSettings: "'FILL' 1" }}>warning</span>
                        <p className="text-sm text-red-400/90">{flag}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Overall Assessment */}
              {vendorData.overall_assessment && (
                <div className="card p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="material-symbols-outlined text-blue-400" style={{ fontVariationSettings: "'FILL' 1" }}>psychology</span>
                    <h3 className="font-bold text-sm text-[var(--text-primary)]">AI Assessment</h3>
                  </div>
                  <MarkdownText text={vendorData.overall_assessment} className="text-sm" />
                </div>
              )}
            </>
          ) : (
            <p className="text-[var(--text-muted)] text-center py-10">Could not load vendor verification.</p>
          )}
        </div>
      )}
    </div>
  );
};

/* ── Analyze View ───────────────────────────────────────────── */

export const AnalyzeView = () => {
  const [pasteMode, setPasteMode] = useState(false);
  const [pasteText, setPasteText] = useState('');
  const [pasteTitle, setPasteTitle] = useState('');
  const [uploadedContract, setUploadedContract] = useState<{ id: string; filename: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const uploadMutation = useMutation({
    mutationFn: uploadContract,
    onSuccess: (data: UploadResponse) => {
      setUploadedContract({ id: data.contract_id, filename: data.filename || 'Uploaded Contract' });
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });

  const ingestMutation = useMutation({
    mutationFn: ({ text, title }: { text: string; title: string }) => ingestText(text, title),
    onSuccess: (data: UploadResponse) => {
      setUploadedContract({ id: data.contract_id, filename: pasteTitle || 'Pasted Contract' });
      setPasteText('');
      setPasteTitle('');
      setPasteMode(false);
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files?.[0]) uploadMutation.mutate(e.dataTransfer.files[0]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) uploadMutation.mutate(e.target.files[0]);
  };

  const handlePasteSubmit = () => {
    if (!pasteText.trim()) return;
    ingestMutation.mutate({ text: pasteText, title: pasteTitle || 'Pasted Contract Text' });
  };

  const handleNewScan = () => {
    setUploadedContract(null);
    uploadMutation.reset();
    ingestMutation.reset();
  };

  const isProcessing = uploadMutation.isPending || ingestMutation.isPending;
  const isError = uploadMutation.isError || ingestMutation.isError;

  return (
    <div className="animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-[var(--text-primary)]">New Scan</h1>
          <p className="text-[var(--text-secondary)] mt-1">
            Upload a contract file or paste text for AI-powered risk analysis and metadata extraction.
          </p>
        </div>
        {uploadedContract && (
          <button onClick={handleNewScan} className="btn-primary px-4 py-2 text-sm flex items-center gap-1.5">
            <span className="material-symbols-outlined text-base">add</span> Scan Another
          </button>
        )}
      </div>

      {/* Upload Section — collapsed after upload */}
      {!uploadedContract && (
        <>
          <div className="card p-6 mb-6">
            <div className="flex items-center gap-1 rounded-xl p-1 mb-5" style={{ background: 'var(--bg-surface)' }}>
              <button onClick={() => setPasteMode(false)}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-bold transition-all ${!pasteMode ? 'text-emerald-400' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}
                style={!pasteMode ? { background: 'var(--accent-glow)', border: '1px solid rgba(16,185,129,0.2)' } : {}}>
                <span className="material-symbols-outlined text-base" style={!pasteMode ? { fontVariationSettings: "'FILL' 1" } : {}}>upload_file</span> File Upload
              </button>
              <button onClick={() => setPasteMode(true)}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-bold transition-all ${pasteMode ? 'text-emerald-400' : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}`}
                style={pasteMode ? { background: 'var(--accent-glow)', border: '1px solid rgba(16,185,129,0.2)' } : {}}>
                <span className="material-symbols-outlined text-base" style={pasteMode ? { fontVariationSettings: "'FILL' 1" } : {}}>content_paste</span> Paste Text
              </button>
            </div>

            {!pasteMode ? (
              <div className="upload-zone p-16 text-center" onDragOver={(e) => e.preventDefault()} onDrop={handleFileDrop}
                onClick={() => fileInputRef.current?.click()}>
                <div className="w-20 h-20 mx-auto rounded-full flex items-center justify-center mb-4" style={{ background: 'var(--accent-glow)' }}>
                  <span className="material-symbols-outlined text-4xl text-emerald-400">cloud_upload</span>
                </div>
                <p className="text-lg font-bold text-[var(--text-primary)] mb-1">Drop contracts here or click to browse</p>
                <p className="text-sm text-[var(--text-muted)]">PDF, DOCX, and TXT files supported</p>
                <div className="mt-6 flex items-center justify-center gap-4">
                  {['PDF', 'DOCX', 'TXT'].map((fmt) => (
                    <span key={fmt} className="px-3 py-1.5 rounded-lg text-xs font-bold text-[var(--text-muted)]"
                      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>.{fmt}</span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2 block">Contract Title</label>
                  <input type="text" className="input-dark w-full" placeholder="e.g. Service Agreement - Acme Corp" value={pasteTitle} onChange={(e) => setPasteTitle(e.target.value)} />
                </div>
                <div>
                  <label className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2 block">Contract Text</label>
                  <textarea className="input-dark w-full h-48 resize-none" placeholder="Paste your contract text here…" value={pasteText} onChange={(e) => setPasteText(e.target.value)} />
                </div>
                <button onClick={handlePasteSubmit} className="btn-primary w-full py-3 flex items-center justify-center gap-2" disabled={!pasteText.trim() || ingestMutation.isPending}>
                  {ingestMutation.isPending ? <><span className="material-symbols-outlined animate-spin text-base">refresh</span> Analyzing…</> : <><span className="material-symbols-outlined text-base">psychology</span> Analyze Contract</>}
                </button>
              </div>
            )}
            <input type="file" ref={fileInputRef} className="hidden" accept=".pdf,.docx,.txt" onChange={handleFileSelect} />
          </div>

          {/* How It Works */}
          <div className="card p-6">
            <h3 className="font-bold text-sm text-[var(--text-primary)] mb-4 flex items-center gap-2">
              <span className="material-symbols-outlined text-emerald-400 text-base" style={{ fontVariationSettings: "'FILL' 1" }}>info</span> How It Works
            </h3>
            <div className="grid grid-cols-4 gap-4">
              {[
                { step: '01', icon: 'upload_file', title: 'Upload', desc: 'Drop your contract file or paste text' },
                { step: '02', icon: 'psychology', title: 'AI Analysis', desc: 'Gemini 2.5 Pro scans for risks & metadata' },
                { step: '03', icon: 'gavel', title: 'Legal Sources', desc: 'Indian Contract Act citations attached' },
                { step: '04', icon: 'forum', title: 'Q&A Ready', desc: 'Ask questions about your contract' },
              ].map((item) => (
                <div key={item.step} className="text-center">
                  <div className="w-10 h-10 mx-auto rounded-lg flex items-center justify-center mb-2" style={{ background: 'var(--accent-glow)', border: '1px solid rgba(16,185,129,0.15)' }}>
                    <span className="material-symbols-outlined text-emerald-400 text-base" style={{ fontVariationSettings: "'FILL' 1" }}>{item.icon}</span>
                  </div>
                  <span className="text-[9px] font-bold text-emerald-500 uppercase tracking-widest">Step {item.step}</span>
                  <p className="text-xs font-bold text-[var(--text-primary)] mt-1">{item.title}</p>
                  <p className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Processing State */}
      {isProcessing && (
        <div className="card-accent p-5 flex items-center gap-3 mb-6 animate-fade-in-up">
          <span className="material-symbols-outlined animate-spin text-emerald-400 text-lg">refresh</span>
          <div>
            <p className="text-sm font-bold text-emerald-400">Processing Contract…</p>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">AI is parsing, indexing, and analyzing. This may take a moment.</p>
          </div>
        </div>
      )}

      {/* Error State */}
      {isError && (
        <div className="p-5 rounded-xl flex items-center gap-3 mb-6" style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <span className="material-symbols-outlined text-red-400 text-lg">error</span>
          <div>
            <p className="text-sm font-bold text-red-400">Upload Failed</p>
            <p className="text-xs text-red-400/60 mt-0.5">{(uploadMutation.error || ingestMutation.error)?.message || 'Please try again.'}</p>
          </div>
        </div>
      )}

      {/* ── Results Panel (shown after successful upload) ── */}
      {uploadedContract && (
        <ResultsPanel contractId={uploadedContract.id} filename={uploadedContract.filename} />
      )}
    </div>
  );
};
