import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  compareContracts,
  type Contract,
  type CompareResponse,
} from '../api';

/* ── Compare View ───────────────────────────────────────────── */

export const CompareView = ({ contracts }: { contracts: Contract[] }) => {
  const readyContracts = contracts.filter((c) => c.status === 'ready');
  const [contractA, setContractA] = useState(readyContracts[0]?.id || '');
  const [contractB, setContractB] = useState(readyContracts[1]?.id || '');
  const [result, setResult] = useState<CompareResponse | null>(null);

  const compareMutation = useMutation({
    mutationFn: () => compareContracts(contractA, contractB),
    onSuccess: (data) => setResult(data),
  });

  const handleCompare = () => {
    if (!contractA || !contractB || contractA === contractB) return;
    setResult(null);
    compareMutation.mutate();
  };

  const getVerdictColor = (verdict: string) => {
    if (verdict === 'favorable') return 'text-emerald-400';
    if (verdict === 'unfavorable') return 'text-red-400';
    if (verdict === 'mixed') return 'text-amber-400';
    return 'text-[var(--text-muted)]';
  };

  return (
    <section className="animate-fade-in-up space-y-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-[var(--text-primary)]">Compare Contracts</h1>
        <p className="text-[var(--text-secondary)] mt-1">Side-by-side analysis of two contracts to find the better deal.</p>
      </div>

      {readyContracts.length < 2 ? (
        <div className="card p-16 text-center">
          <span className="material-symbols-outlined text-6xl text-[var(--text-muted)] mb-4 opacity-30" style={{ fontVariationSettings: "'FILL' 1" }}>
            compare_arrows
          </span>
          <p className="font-bold text-[var(--text-secondary)] text-lg">Need at least 2 contracts</p>
          <p className="text-sm text-[var(--text-muted)] mt-2">
            Upload and analyze at least two contracts to compare them side by side.
          </p>
        </div>
      ) : (
        <>
          {/* Selector */}
          <div className="card p-6">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
              <div className="md:col-span-2">
                <label className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2 block">
                  Contract A
                </label>
                <select
                  value={contractA}
                  onChange={(e) => setContractA(e.target.value)}
                  className="input-dark w-full"
                >
                  {readyContracts.map((c) => (
                    <option key={c.id} value={c.id}>{c.filename}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-center">
                <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: 'var(--bg-elevated)' }}>
                  <span className="material-symbols-outlined text-[var(--text-muted)]">compare_arrows</span>
                </div>
              </div>

              <div className="md:col-span-2">
                <label className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2 block">
                  Contract B
                </label>
                <select
                  value={contractB}
                  onChange={(e) => setContractB(e.target.value)}
                  className="input-dark w-full"
                >
                  {readyContracts.map((c) => (
                    <option key={c.id} value={c.id}>{c.filename}</option>
                  ))}
                </select>
              </div>
            </div>

            <button
              onClick={handleCompare}
              disabled={!contractA || !contractB || contractA === contractB || compareMutation.isPending}
              className="btn-primary w-full mt-5 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {compareMutation.isPending ? (
                <><span className="material-symbols-outlined animate-spin text-base">refresh</span> Comparing…</>
              ) : (
                <><span className="material-symbols-outlined text-base">compare_arrows</span> Compare Selected Contracts</>
              )}
            </button>

            {contractA === contractB && contractA && (
              <p className="text-xs text-amber-400 font-medium mt-2 text-center">Please select two different contracts.</p>
            )}
            {compareMutation.isError && (
              <p className="text-xs text-red-400 font-medium mt-2 text-center">Comparison failed. Please try again.</p>
            )}
          </div>

          {/* Results */}
          {result && result.details && (
            <div className="space-y-6 animate-fade-in-up">
              {/* Winner Banner */}
              <div className="card-cta rounded-xl px-6 py-5 flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-white/70">Comparison Result</p>
                  <p className="text-2xl font-black text-white mt-1">
                    {result.details.winner === 'Tie'
                      ? 'Both Contracts Are Similarly Balanced'
                      : `${result.details.winner} is More Favorable`}
                  </p>
                </div>
                <span className="material-symbols-outlined text-4xl text-white/40" style={{ fontVariationSettings: "'FILL' 1" }}>
                  {result.details.winner === 'Tie' ? 'balance' : 'emoji_events'}
                </span>
              </div>

              {/* Executive Summary */}
              <div className="card p-6">
                <h3 className="font-bold flex items-center gap-2 mb-3 text-[var(--text-primary)]">
                  <span className="material-symbols-outlined text-emerald-400" style={{ fontVariationSettings: "'FILL' 1" }}>summarize</span>
                  Executive Summary
                </h3>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  {result.summary || result.details.summary || 'No summary available.'}
                </p>
              </div>

              {/* Risk Score Comparison */}
              {result.details.risk_comparison && (
                <div className="card overflow-hidden">
                  <div className="px-6 py-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <h3 className="font-bold flex items-center gap-2 text-[var(--text-primary)]">
                      <span className="material-symbols-outlined text-amber-400" style={{ fontVariationSettings: "'FILL' 1" }}>shield</span>
                      Risk Score Comparison
                    </h3>
                  </div>
                  <div className="p-6">
                    <div className="grid grid-cols-3 gap-6">
                      {/* Contract A */}
                      <div className="text-center space-y-3">
                        <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">Contract A</p>
                        <div className="mx-auto w-24 h-24 rounded-full border-2 border-emerald-500/30 flex flex-col items-center justify-center" style={{ background: 'rgba(16,185,129,0.08)' }}>
                          <p className="text-2xl font-black text-emerald-400">
                            {result.details.risk_comparison.contract_a_safety_score}
                          </p>
                          <p className="text-[9px] font-bold text-emerald-500 uppercase">Safety</p>
                        </div>
                        <p className="text-xs font-bold text-[var(--text-secondary)]">
                          Risk: {result.details.risk_comparison.contract_a_risk_score}/100
                        </p>
                        {result.details.risk_comparison.contract_a_risk_level && (
                          <p className="text-xs text-[var(--text-muted)]">{result.details.risk_comparison.contract_a_risk_level}</p>
                        )}
                      </div>

                      {/* VS */}
                      <div className="flex flex-col items-center justify-center">
                        <p className="text-xs font-bold text-[var(--text-muted)] mb-3">VS</p>
                        <div className="card-elevated rounded-xl px-4 py-3 text-center">
                          <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-1">Safer Contract</p>
                          <p className="text-lg font-black text-[var(--text-primary)]">{result.details.risk_comparison.safer_contract}</p>
                          <p className="text-xs text-[var(--text-muted)] mt-1">Gap: {result.details.risk_comparison.safety_score_gap} pts</p>
                        </div>
                      </div>

                      {/* Contract B */}
                      <div className="text-center space-y-3">
                        <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">Contract B</p>
                        <div className="mx-auto w-24 h-24 rounded-full border-2 border-purple-500/30 flex flex-col items-center justify-center" style={{ background: 'rgba(168,85,247,0.08)' }}>
                          <p className="text-2xl font-black text-purple-400">
                            {result.details.risk_comparison.contract_b_safety_score}
                          </p>
                          <p className="text-[9px] font-bold text-purple-500 uppercase">Safety</p>
                        </div>
                        <p className="text-xs font-bold text-[var(--text-secondary)]">
                          Risk: {result.details.risk_comparison.contract_b_risk_score}/100
                        </p>
                        {result.details.risk_comparison.contract_b_risk_level && (
                          <p className="text-xs text-[var(--text-muted)]">{result.details.risk_comparison.contract_b_risk_level}</p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Category Breakdown */}
              {result.details.category_comparison && result.details.category_comparison.length > 0 && (
                <div className="card overflow-hidden">
                  <div className="px-6 py-4" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <h3 className="font-bold flex items-center gap-2 text-[var(--text-primary)]">
                      <span className="material-symbols-outlined text-blue-400" style={{ fontVariationSettings: "'FILL' 1" }}>analytics</span>
                      Category Breakdown
                    </h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <thead>
                        <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                          <th className="px-6 py-3 table-header">Dimension</th>
                          <th className="px-6 py-3 table-header text-center">Contract A</th>
                          <th className="px-6 py-3 table-header text-center">Contract B</th>
                          <th className="px-6 py-3 table-header text-center">Better</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.details.category_comparison.map((cat, idx) => (
                          <tr key={idx} className="table-row">
                            <td className="px-6 py-3">
                              <span className="font-bold text-sm text-[var(--text-primary)]">{cat.label}</span>
                            </td>
                            <td className="px-6 py-3 text-center">
                              <span className={`text-sm font-bold capitalize ${getVerdictColor(cat.contract_a_verdict)}`}>
                                {cat.contract_a_verdict}
                              </span>
                            </td>
                            <td className="px-6 py-3 text-center">
                              <span className={`text-sm font-bold capitalize ${getVerdictColor(cat.contract_b_verdict)}`}>
                                {cat.contract_b_verdict}
                              </span>
                            </td>
                            <td className="px-6 py-3 text-center">
                              <span className={`px-2.5 py-0.5 rounded-md text-xs font-bold ${
                                cat.better_contract === 'A'
                                  ? 'bg-emerald-500/10 text-emerald-400'
                                  : cat.better_contract === 'B'
                                    ? 'bg-purple-500/10 text-purple-400'
                                    : 'text-[var(--text-muted)]'
                              }`} style={cat.better_contract !== 'A' && cat.better_contract !== 'B' ? { background: 'var(--bg-elevated)' } : {}}>
                                {cat.better_contract === 'A' ? 'Contract A' : cat.better_contract === 'B' ? 'Contract B' : 'Tie'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Key Differences */}
              {result.details.key_differences && result.details.key_differences.length > 0 && (
                <div className="space-y-4">
                  <h3 className="font-bold flex items-center gap-2 text-[var(--text-primary)]">
                    <span className="material-symbols-outlined text-rose-400" style={{ fontVariationSettings: "'FILL' 1" }}>difference</span>
                    Key Differences
                  </h3>
                  {result.details.key_differences.map((diff, idx) => (
                    <div key={idx} className="card p-5">
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="font-bold text-sm text-[var(--text-primary)]">{diff.dimension}</h4>
                        <span className={`px-2.5 py-0.5 rounded-md text-xs font-bold ${
                          diff.better_contract === 'A'
                            ? 'bg-emerald-500/10 text-emerald-400'
                            : diff.better_contract === 'B'
                              ? 'bg-purple-500/10 text-purple-400'
                              : 'text-[var(--text-muted)]'
                        }`} style={diff.better_contract !== 'A' && diff.better_contract !== 'B' ? { background: 'var(--bg-elevated)' } : {}}>
                          {diff.better_contract === 'A' ? 'Contract A Better' : diff.better_contract === 'B' ? 'Contract B Better' : 'Tie'}
                        </span>
                      </div>

                      {diff.explanation && (
                        <p className="text-sm text-[var(--text-secondary)] mb-3 leading-relaxed">{diff.explanation}</p>
                      )}

                      <div className="grid grid-cols-2 gap-3">
                        {diff.contract_a_evidence && (
                          <div className="rounded-lg px-3 py-2" style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)' }}>
                            <p className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest mb-1">Contract A</p>
                            <p className="text-xs text-emerald-300/80 leading-relaxed italic">"{diff.contract_a_evidence}"</p>
                          </div>
                        )}
                        {diff.contract_b_evidence && (
                          <div className="rounded-lg px-3 py-2" style={{ background: 'rgba(168,85,247,0.06)', border: '1px solid rgba(168,85,247,0.15)' }}>
                            <p className="text-[10px] font-bold text-purple-400 uppercase tracking-widest mb-1">Contract B</p>
                            <p className="text-xs text-purple-300/80 leading-relaxed italic">"{diff.contract_b_evidence}"</p>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
};
