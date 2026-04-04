import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { type Contract, compareContracts } from '../api';

export const CompareView = ({ contracts }: { contracts: Contract[] }) => {
  const [docAId, setDocAId] = useState<string>('');
  const [docBId, setDocBId] = useState<string>('');
  
  const readyContracts = contracts.filter(c => c.status === 'ready');

  const { data: comparison, isLoading, refetch } = useQuery({
    queryKey: ['compare', docAId, docBId],
    queryFn: () => compareContracts(docAId, docBId),
    enabled: false, // only run when button is clicked
  });

  const handleCompare = () => {
    if (docAId && docBId && docAId !== docBId) {
      refetch();
    }
  };

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4">
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-on-background mb-2 flex items-center gap-2">
          <span className="material-symbols-outlined text-primary">compare_arrows</span>
          Side-by-Side Comparison
        </h2>
        <p className="text-secondary text-sm">Select two verified contracts to generate an AI deviation analysis.</p>
      </div>

      <div className="bg-surface-container-lowest p-6 rounded-xl border border-outline-variant/30 shadow-sm mb-8">
        <div className="flex flex-col md:flex-row gap-6 items-end">
          <div className="flex-1 w-full">
            <label className="block text-xs font-bold uppercase tracking-widest text-secondary mb-2">Base Document (A)</label>
            <select 
              value={docAId} 
              onChange={e => setDocAId(e.target.value)}
              className="w-full bg-surface-container-low border border-outline-variant/50 rounded-lg p-3 text-sm focus:outline-none focus:border-primary shadow-sm"
            >
              <option value="">-- Select Contract --</option>
              {readyContracts.map(c => <option key={c.id} value={c.id}>{c.filename}</option>)}
            </select>
          </div>
          
          <div className="hidden md:flex items-center justify-center p-2 text-outline-variant">
            <span className="material-symbols-outlined">sync_alt</span>
          </div>

          <div className="flex-1 w-full">
            <label className="block text-xs font-bold uppercase tracking-widest text-secondary mb-2">Target Document (B)</label>
            <select 
              value={docBId} 
              onChange={e => setDocBId(e.target.value)}
              className="w-full bg-surface-container-low border border-outline-variant/50 rounded-lg p-3 text-sm focus:outline-none focus:border-primary shadow-sm"
            >
              <option value="">-- Select Contract --</option>
              {readyContracts.map(c => <option key={c.id} value={c.id}>{c.filename}</option>)}
            </select>
          </div>
          
          <button 
            onClick={handleCompare}
            disabled={!docAId || !docBId || docAId === docBId || isLoading}
            className="w-full md:w-auto px-8 py-3 bg-primary text-on-primary rounded-lg font-bold disabled:opacity-50 hover:bg-primary-container hover:text-on-primary-container transition-all"
          >
            {isLoading ? 'Analyzing...' : 'Run Comparison'}
          </button>
        </div>
        
        {docAId && docBId && docAId === docBId && (
          <p className="text-error text-xs font-bold mt-4 flex items-center gap-1">
            <span className="material-symbols-outlined text-[14px]">error</span>
            Please select two different documents to compare.
          </p>
        )}
      </div>

      {isLoading && (
        <div className="flex flex-col items-center justify-center py-20 opacity-50">
          <span className="material-symbols-outlined text-4xl animate-spin text-primary mb-4">settings</span>
          <p className="text-secondary font-bold animate-pulse">Running Deep Semantic Alignment on Clauses...</p>
        </div>
      )}

      {comparison && !isLoading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in slide-in-from-bottom-4">
          <div className="lg:col-span-2 bg-surface-container-low border border-outline-variant/30 rounded-xl p-6">
            <h3 className="text-lg font-bold flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined text-tertiary">summarize</span>
              Executive Deviation Summary
            </h3>
            <p className="text-on-surface leading-relaxed">{comparison.summary}</p>
          </div>
          
          <div className="bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-6 shadow-sm">
            <h4 className="font-bold text-on-surface mb-4 pb-2 border-b border-outline-variant/20">Missing in A (Added in B)</h4>
            {comparison.details?.missing_in_a?.length === 0 ? (
              <p className="text-secondary text-sm italic">No missing clauses detected.</p>
            ) : (
              <ul className="space-y-3">
                {comparison.details?.missing_in_a?.map((item: any, i: number) => (
                  <li key={i} className="text-sm bg-blue-50/50 dark:bg-blue-900/10 p-3 rounded border border-blue-100 dark:border-blue-900/30 text-on-surface">
                    {item.clause || item}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-6 shadow-sm">
            <h4 className="font-bold text-on-surface mb-4 pb-2 border-b border-outline-variant/20">Missing in B (Removed from A)</h4>
            {comparison.details?.missing_in_b?.length === 0 ? (
              <p className="text-secondary text-sm italic">No missing clauses detected.</p>
            ) : (
              <ul className="space-y-3">
                {comparison.details?.missing_in_b?.map((item: any, i: number) => (
                  <li key={i} className="text-sm bg-red-50/50 dark:bg-red-900/10 p-3 rounded border border-red-100 dark:border-red-900/30 text-on-surface">
                    {item.clause || item}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
