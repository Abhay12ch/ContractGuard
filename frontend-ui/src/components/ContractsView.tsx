import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchSummary,
  fetchRisks,
  fetchMetadata,
  fetchVendorVerification,
  askQuestion,
  deleteContract,
  type Contract,
  type RiskItem,
  type MetadataField,
  type VendorVerificationCheck,
} from '../api';
import { MarkdownText } from './MarkdownText';

/* ── Gauge Component ────────────────────────────────────────── */

const RiskGauge = ({ score }: { score: number }) => {
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  let strokeColor = '#ef4444';
  if (score >= 80) strokeColor = '#10b981';
  else if (score >= 60) strokeColor = '#f59e0b';
  else if (score >= 40) strokeColor = '#f97316';

  return (
    <div className="relative w-32 h-32 mx-auto">
      <svg width="128" height="128" viewBox="0 0 128 128">
        <circle cx="64" cy="64" r={radius} fill="none" stroke="var(--border-subtle)" strokeWidth="8" />
        <circle
          cx="64" cy="64" r={radius} fill="none"
          stroke={strokeColor} strokeWidth="8"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-1000"
          style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <p className="text-3xl font-black" style={{ color: strokeColor }}>{score}</p>
        <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Safety</p>
      </div>
    </div>
  );
};

/* ── Severity Badge ─────────────────────────────────────────── */

const SeverityBadge = ({ severity }: { severity: string }) => {
  const s = severity.toLowerCase();
  let cls = 'severity-low';
  if (s === 'high') cls = 'severity-high';
  else if (s === 'medium') cls = 'severity-medium';
  return (
    <span className={`${cls} px-2.5 py-0.5 rounded-md text-xs font-bold uppercase tracking-wide`}>
      {severity}
    </span>
  );
};

/* ── Risk Level Badge ───────────────────────────────────────── */

const RiskLevelBadge = ({ level }: { level: string }) => {
  const l = level.toLowerCase();
  let cls = 'severity-low';
  if (l.includes('very high')) cls = 'severity-high';
  else if (l.includes('high')) cls = 'severity-high';
  else if (l.includes('moderate')) cls = 'severity-medium';
  return (
    <span className={`${cls} px-4 py-1.5 rounded-lg text-sm font-bold inline-flex items-center gap-1.5`}>
      <span className="material-symbols-outlined text-base">
        {l.includes('low') ? 'verified_user' : l.includes('moderate') ? 'warning' : 'gpp_bad'}
      </span>
      {level}
    </span>
  );
};

/* ── Confidence Bar ─────────────────────────────────────────── */

const ConfidenceBar = ({ confidence }: { confidence: number }) => {
  let color = 'bg-red-500';
  if (confidence >= 70) color = 'bg-emerald-500';
  else if (confidence >= 40) color = 'bg-amber-500';
  return (
    <div className="flex items-center gap-2">
      <div className="confidence-bar flex-1">
        <div className={`confidence-bar-fill ${color}`} style={{ width: `${confidence}%`, background: undefined }} />
      </div>
      <span className="text-xs font-bold text-[var(--text-muted)] w-8 text-right">{confidence}%</span>
    </div>
  );
};

/* ── Metadata Field Labels ──────────────────────────────────── */

const FIELD_LABELS: Record<string, { label: string; icon: string; group: string }> = {
  customer_name: { label: 'Customer Name', icon: 'person', group: 'Parties' },
  vendor_name: { label: 'Vendor Name', icon: 'storefront', group: 'Parties' },
  contract_type: { label: 'Contract Type', icon: 'category', group: 'Contract Info' },
  governing_law: { label: 'Governing Law', icon: 'gavel', group: 'Contract Info' },
  effective_date: { label: 'Effective Date', icon: 'event', group: 'Dates' },
  expiration_date: { label: 'Expiration Date', icon: 'event_busy', group: 'Dates' },
  payment_terms: { label: 'Payment Terms', icon: 'payments', group: 'Financial' },
  billing_cycle: { label: 'Billing Cycle', icon: 'schedule', group: 'Financial' },
  total_value: { label: 'Total Value', icon: 'attach_money', group: 'Financial' },
  renewal_terms: { label: 'Renewal Terms', icon: 'autorenew', group: 'Terms' },
};

/* ── Loading Skeleton ───────────────────────────────────────── */

const Skeleton = ({ className = '' }: { className?: string }) => (
  <div className={`skeleton ${className}`} />
);

/* ── Document Detail ────────────────────────────────────────── */

const DocumentDetail = ({
  contract,
  onClose,
}: {
  contract: Contract;
  onClose: () => void;
}) => {
  const [activeTab, setActiveTab] = useState<'summary' | 'risks' | 'metadata' | 'vendor' | 'chat'>('summary');
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState<{ question: string; answer: string; chunks?: number }[]>([]);
  const [sessionId, setSessionId] = useState('');

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['summary', contract.id],
    queryFn: () => fetchSummary(contract.id),
    staleTime: 300000,
  });

  const { data: risks, isLoading: risksLoading } = useQuery({
    queryKey: ['risks', contract.id],
    queryFn: () => fetchRisks(contract.id),
    staleTime: 300000,
  });

  const { data: metadata, isLoading: metadataLoading } = useQuery({
    queryKey: ['metadata', contract.id],
    queryFn: () => fetchMetadata(contract.id),
    staleTime: 300000,
  });

  const { data: vendorData, isLoading: vendorLoading } = useQuery({
    queryKey: ['vendor', contract.id],
    queryFn: () => fetchVendorVerification(contract.id),
    staleTime: 300000,
  });

  const askMutation = useMutation({
    mutationFn: (question: string) => askQuestion(contract.id, question, sessionId),
    onSuccess: (data) => {
      setChatHistory((prev) => [
        ...prev,
        { question: data.question, answer: data.answer, chunks: data.retrieved_chunks_count },
      ]);
      setSessionId(data.session_id || sessionId);
      setChatInput('');
    },
  });

  const quickQuestions = [
    'What are the termination conditions?',
    'Are there any auto-renewal clauses?',
    'What liability limits are defined?',
  ];

  const tabs = [
    { key: 'summary' as const, icon: 'summarize', label: 'Summary' },
    { key: 'risks' as const, icon: 'shield', label: 'Risks' },
    { key: 'metadata' as const, icon: 'database', label: 'Metadata' },
    { key: 'vendor' as const, icon: 'verified_user', label: 'Vendor Trust' },
    { key: 'chat' as const, icon: 'forum', label: 'Chat' },
  ];

  // Metadata KPIs
  const metadataFields = metadata?.metadata || {};
  const extractedCount = Object.values(metadataFields).filter(
    (f: MetadataField) => f.value && f.value.trim()
  ).length;
  const totalFields = Object.keys(metadataFields).length || 10;
  const avgConfidence =
    totalFields > 0
      ? Math.round(
          Object.values(metadataFields).reduce((s: number, f: MetadataField) => s + f.confidence, 0) /
            totalFields
        )
      : 0;

  return (
    <div className="animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-lg flex items-center justify-center transition-colors"
            style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}
          >
            <span className="material-symbols-outlined text-lg text-[var(--text-secondary)]">arrow_back</span>
          </button>
          <div>
            <h2 className="text-xl font-black text-[var(--text-primary)]">{contract.filename}</h2>
            <p className="text-xs text-[var(--text-muted)] font-mono">{contract.id}</p>
          </div>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 rounded-xl p-1 mb-6" style={{ background: 'var(--bg-card)' }}>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-sm font-bold transition-all ${
              activeTab === tab.key
                ? 'text-emerald-400'
                : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
            }`}
            style={activeTab === tab.key ? { background: 'var(--accent-glow)', border: '1px solid rgba(16,185,129,0.2)' } : {}}
          >
            <span
              className="material-symbols-outlined text-base"
              style={activeTab === tab.key ? { fontVariationSettings: "'FILL' 1" } : undefined}
            >
              {tab.icon}
            </span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab: Summary ─────────────────────────────────── */}
      {activeTab === 'summary' && (
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-emerald-400" style={{ fontVariationSettings: "'FILL' 1" }}>
              summarize
            </span>
            <h3 className="font-bold text-lg text-[var(--text-primary)]">AI-Generated Summary</h3>
          </div>
          {summaryLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/6" />
            </div>
          ) : (
            <MarkdownText text={summary || 'No summary available.'} />
          )}
        </div>
      )}

      {/* ── Tab: Risks ───────────────────────────────────── */}
      {activeTab === 'risks' && (
        <div className="space-y-5">
          {risksLoading ? (
            <div className="space-y-4"><Skeleton className="h-40 w-full" /><Skeleton className="h-24 w-full" /><Skeleton className="h-24 w-full" /></div>
          ) : risks ? (
            <>
              {/* Score Panel */}
              <div className="card p-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
                  <div className="flex flex-col items-center"><RiskGauge score={risks.safety_score} /></div>
                  <div className="flex flex-col items-center gap-3">
                    <RiskLevelBadge level={risks.risk_level} />
                    <div className="text-center mt-2">
                      <p className="text-3xl font-black text-[var(--text-primary)]">{risks.detected_clause_count}</p>
                      <p className="text-xs text-[var(--text-muted)] font-bold uppercase tracking-widest">Risky Clauses</p>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div className="card-elevated rounded-lg p-3">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-400/60 mb-0.5 flex items-center gap-1"><span className="material-symbols-outlined text-[10px]">verified_user</span> Safety Score</p>
                      <p className="text-lg font-black text-emerald-400">{risks.safety_score}<span className="text-sm text-[var(--text-muted)]">/100</span></p>
                      <p className="text-[9px] text-[var(--text-muted)] mt-0.5">Higher = Safer</p>
                    </div>
                    <div className="card-elevated rounded-lg p-3">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-red-400/60 mb-0.5 flex items-center gap-1"><span className="material-symbols-outlined text-[10px]">warning</span> Risk Score</p>
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
                  <span className="material-symbols-outlined text-4xl text-emerald-400 mb-2" style={{ fontVariationSettings: "'FILL' 1" }}>verified_user</span>
                  <p className="font-bold text-emerald-400">No risky clauses detected</p>
                  <p className="text-sm text-[var(--text-muted)] mt-1">This contract appears safe based on the analysis.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <h4 className="font-bold text-xs text-[var(--text-muted)] uppercase tracking-widest">Detected Clauses ({risks.risks.length})</h4>
                  {risks.risks.map((risk: RiskItem, idx: number) => {
                    const borderColor = risk.severity === 'High' ? '#ef4444' : risk.severity === 'Medium' ? '#f59e0b' : '#60a5fa';
                    return (
                      <div key={idx} className="card overflow-hidden hover:border-[var(--border-default)] transition-all" style={{ borderLeft: `3px solid ${borderColor}` }}>
                        <div className="p-5">
                          <div className="flex items-start justify-between gap-4 mb-3">
                            <div className="flex items-center gap-2.5">
                              <span className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold" style={{ background: `${borderColor}15`, color: borderColor }}>{idx + 1}</span>
                              <h5 className="font-bold text-[var(--text-primary)]">{risk.title}</h5>
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              <SeverityBadge severity={risk.severity} />
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-md" style={{ background: `${borderColor}12`, color: borderColor }}>Impact: {risk.impact}</span>
                            </div>
                          </div>
                          {risk.explanation && <div className="mb-3"><MarkdownText text={risk.explanation} className="text-sm" /></div>}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                            {risk.evidence && (
                              <div className="rounded-lg px-3.5 py-2.5" style={{ background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.12)' }}>
                                <p className="text-[9px] font-bold text-amber-500/70 uppercase tracking-widest mb-1 flex items-center gap-1"><span className="material-symbols-outlined text-[10px]">format_quote</span> Evidence</p>
                                <p className="text-xs text-amber-400/80 italic leading-relaxed">"{risk.evidence}"</p>
                              </div>
                            )}
                            {risk.source && (
                              <div className="rounded-lg px-3.5 py-2.5" style={{ background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.12)' }}>
                                <p className="text-[9px] font-bold text-blue-400/70 uppercase tracking-widest mb-1 flex items-center gap-1"><span className="material-symbols-outlined text-[10px]">menu_book</span> Legal Source</p>
                                <p className="text-xs text-blue-300/80 leading-relaxed">{risk.source}</p>
                                {risk.source_url && (
                                  <a href={risk.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-bold text-blue-400 hover:text-blue-300 transition-colors">
                                    <span className="material-symbols-outlined text-xs">open_in_new</span> View Legal Text →
                                  </a>
                                )}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-3">
                            <span className="text-[10px] font-bold text-[var(--text-muted)] px-2 py-0.5 rounded-md" style={{ background: 'var(--bg-elevated)' }}>{risk.clause_type}</span>
                            {risk.keyword && <span className="text-[10px] font-bold text-[var(--text-muted)] px-2 py-0.5 rounded-md" style={{ background: 'var(--bg-elevated)' }}>keyword: {risk.keyword}</span>}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          ) : (
            <p className="text-[var(--text-muted)] text-center py-10">Could not load risk analysis.</p>
          )}
        </div>
      )}

      {/* ── Tab: Metadata ────────────────────────────────── */}
      {activeTab === 'metadata' && (
        <div className="space-y-5">
          {metadataLoading ? (
            <div className="space-y-4"><Skeleton className="h-24 w-full" /><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
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
                      <span className="material-symbols-outlined text-emerald-400 text-base" style={{ fontVariationSettings: "'FILL' 1" }}>{groupIcons[groupName] || 'folder'}</span>
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
                                  style={hasValue ? { fontVariationSettings: "'FILL' 1" } : undefined}>{info.icon}</span>
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
          ) : (
            <p className="text-[var(--text-muted)] text-center py-10">Could not load metadata.</p>
          )}
        </div>
      )}

      {/* ── Tab: Chat ────────────────────────────────────── */}
      {activeTab === 'chat' && (
        <div className="space-y-4">
          {/* Quick Questions */}
          <div className="flex flex-wrap gap-2">
            {quickQuestions.map((q) => (
              <button
                key={q}
                onClick={() => {
                  setChatInput(q);
                  askMutation.mutate(q);
                }}
                disabled={askMutation.isPending}
                className="px-3 py-1.5 rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
                style={{ background: 'var(--accent-glow)', color: 'var(--accent-light)', border: '1px solid rgba(16,185,129,0.2)' }}
              >
                {q}
              </button>
            ))}
          </div>

          {/* Chat History */}
          <div className="card min-h-[300px] max-h-[500px] overflow-y-auto p-6 space-y-4">
            {chatHistory.length === 0 && !askMutation.isPending && (
              <div className="text-center py-12">
                <span className="material-symbols-outlined text-5xl text-[var(--text-muted)] mb-3 opacity-30" style={{ fontVariationSettings: "'FILL' 1" }}>
                  forum
                </span>
                <p className="text-sm text-[var(--text-secondary)] font-medium">
                  Ask a question about this contract
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-1">The AI will search the contract to answer</p>
              </div>
            )}
            {chatHistory.map((item, idx) => (
              <div key={idx} className="space-y-3 animate-fade-in-up">
                {/* Question */}
                <div className="flex justify-end">
                  <div className="bg-emerald-600 text-white px-4 py-2.5 rounded-2xl rounded-tr-md max-w-[80%]">
                    <p className="text-sm">{item.question}</p>
                  </div>
                </div>
                {/* Answer */}
                <div className="flex justify-start">
                  <div className="px-4 py-3 rounded-2xl rounded-tl-md max-w-[80%]" style={{ background: 'var(--bg-elevated)' }}>
                    <MarkdownText text={item.answer} className="text-sm" />
                    {item.chunks !== undefined && (
                      <p className="text-[10px] text-[var(--text-muted)] mt-2 font-bold">
                        Based on {item.chunks} retrieved chunks
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {askMutation.isPending && (
              <div className="flex justify-start">
                <div className="px-4 py-3 rounded-2xl rounded-tl-md" style={{ background: 'var(--bg-elevated)' }}>
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined animate-spin text-sm text-[var(--text-muted)]">refresh</span>
                    <p className="text-sm text-[var(--text-muted)]">Searching contract…</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input */}
          <div className="flex gap-2">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && chatInput.trim() && !askMutation.isPending) {
                  askMutation.mutate(chatInput.trim());
                }
              }}
              placeholder="Ask about this contract…"
              className="input-dark flex-1"
            />
            <button
              onClick={() => {
                if (chatInput.trim()) askMutation.mutate(chatInput.trim());
              }}
              disabled={!chatInput.trim() || askMutation.isPending}
              className="btn-primary px-5 flex items-center gap-1.5 disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-base">send</span>
              Ask
            </button>
          </div>
          {askMutation.isError && (
            <p className="text-xs text-red-400 font-medium">
              Failed to get an answer. The contract may still be indexing — try again shortly.
            </p>
          )}
        </div>
      )}

      {/* ── Tab: Vendor Trust ────────────────────────────── */}
      {activeTab === 'vendor' && (
        <div className="space-y-5">
          {vendorLoading ? (
            <div className="space-y-4"><Skeleton className="h-40 w-full" /><Skeleton className="h-24 w-full" /></div>
          ) : vendorData ? (
            <>
              <div className="card p-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
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
                        <span className="text-3xl font-black" style={{ color: vendorData.trust_score >= 75 ? '#10b981' : vendorData.trust_score >= 40 ? '#f59e0b' : '#ef4444' }}>{vendorData.trust_score}</span>
                        <span className="text-[9px] font-bold text-[var(--text-muted)] uppercase">Trust Score</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col items-center gap-3">
                    <div className={`px-4 py-1.5 rounded-full text-xs font-black uppercase tracking-widest ${
                      vendorData.trust_level === 'Verified' ? 'bg-emerald-500/15 text-emerald-400' :
                      vendorData.trust_level === 'Caution' ? 'bg-amber-500/15 text-amber-400' : 'bg-red-500/15 text-red-400'
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
              <div className="card overflow-hidden">
                <div className="px-5 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <span className="material-symbols-outlined text-emerald-400 text-base" style={{ fontVariationSettings: "'FILL' 1" }}>checklist</span>
                  <h3 className="font-bold text-sm text-[var(--text-primary)]">Verification Checks</h3>
                  <span className="text-[10px] font-bold text-[var(--text-muted)] ml-auto">{vendorData.checks.filter((c: VendorVerificationCheck) => c.passed).length}/{vendorData.checks.length} passed</span>
                </div>
                {vendorData.checks.map((check: VendorVerificationCheck, idx: number) => (
                  <div key={idx} className="px-5 py-3.5 hover:bg-[var(--bg-card-hover)] transition-colors"
                    style={idx < vendorData.checks.length - 1 ? { borderBottom: '1px solid var(--border-subtle)' } : {}}>
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${check.passed ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                        <span className={`material-symbols-outlined text-sm ${check.passed ? 'text-emerald-400' : 'text-red-400'}`} style={{ fontVariationSettings: "'FILL' 1" }}>{check.passed ? 'check_circle' : 'cancel'}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-bold text-[var(--text-primary)]">{check.check}</p>
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${check.passed ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>+{check.points}/{check.max_points}</span>
                        </div>
                        <p className="text-xs text-[var(--text-muted)] mt-0.5 leading-relaxed">{check.detail}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
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

/* ── Contracts Grid View ────────────────────────────────────── */

export const ContractsView = ({ contracts }: { contracts: Contract[] }) => {
  const [selectedContract, setSelectedContract] = useState<Contract | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: deleteContract,
    onSuccess: () => {
      setConfirmDeleteId(null);
      setSelectedContract(null);
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });

  if (selectedContract) {
    return <DocumentDetail contract={selectedContract} onClose={() => setSelectedContract(null)} />;
  }

  const readyContracts = contracts.filter((c) => c.status === 'ready');

  return (
    <section className="animate-fade-in-up">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[var(--text-primary)]">Analysis History</h1>
        <p className="text-[var(--text-secondary)] mt-1">Review your past contract scans and their results.</p>
      </div>

      {readyContracts.length === 0 ? (
        <div className="card p-16 text-center">
          <span className="material-symbols-outlined text-6xl text-[var(--text-muted)] mb-4 opacity-30" style={{ fontVariationSettings: "'FILL' 1" }}>
            folder_off
          </span>
          <p className="font-bold text-[var(--text-secondary)] text-lg">No contracts analyzed yet</p>
          <p className="text-sm text-[var(--text-muted)] mt-2">Upload a contract from the Overview to get started</p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-left">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <th className="px-5 py-3 table-header">Source / File Name</th>
                <th className="px-5 py-3 table-header">Classification</th>
                <th className="px-5 py-3 table-header">Status</th>
                <th className="px-5 py-3 table-header">Date & Time</th>
                <th className="px-5 py-3 table-header text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {readyContracts.map((contract) => (
                <tr
                  key={contract.id}
                  className="table-row"
                >
                  <td className="px-5 py-4 cursor-pointer" onClick={() => setSelectedContract(contract)}>
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${contract.filename.endsWith('.pdf') ? 'bg-red-500/10' : 'bg-blue-500/10'}`}>
                        <span className={`material-symbols-outlined text-sm ${contract.filename.endsWith('.pdf') ? 'text-red-400' : 'text-blue-400'}`}>
                          {contract.filename.endsWith('.pdf') ? 'picture_as_pdf' : 'description'}
                        </span>
                      </div>
                      <div>
                        <p className="font-semibold text-sm text-[var(--text-primary)]">{contract.filename}</p>
                        <p className="text-[10px] text-[var(--text-muted)] font-mono mt-0.5">{contract.id.slice(0, 16)}…</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-4 cursor-pointer" onClick={() => setSelectedContract(contract)}>
                    <span className="badge badge-ready">ANALYZED</span>
                  </td>
                  <td className="px-5 py-4 cursor-pointer" onClick={() => setSelectedContract(contract)}>
                    <span className="badge badge-ready">READY</span>
                  </td>
                  <td className="px-5 py-4 cursor-pointer" onClick={() => setSelectedContract(contract)}>
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
                  <td className="px-5 py-4 text-right">
                    {confirmDeleteId === contract.id ? (
                      <div className="flex items-center justify-end gap-2">
                        <span className="text-xs text-red-400 font-semibold">Delete?</span>
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(contract.id); }}
                          disabled={deleteMutation.isPending}
                          className="px-2.5 py-1 rounded-lg text-xs font-bold text-white bg-red-500 hover:bg-red-600 transition-colors disabled:opacity-50"
                        >
                          {deleteMutation.isPending ? '…' : 'Yes'}
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(null); }}
                          className="px-2.5 py-1 rounded-lg text-xs font-bold text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                          style={{ background: 'var(--bg-elevated)' }}
                        >
                          No
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(contract.id); }}
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-[var(--text-muted)] hover:text-red-400 hover:bg-red-500/10 transition-all"
                        title="Delete contract"
                      >
                        <span className="material-symbols-outlined text-base">delete</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
