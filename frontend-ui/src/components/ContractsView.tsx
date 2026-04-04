import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { type Contract, fetchSummary, fetchRisks, askQuestion } from '../api';

const DocumentDetail = ({ contract, onClose }: { contract: Contract; onClose: () => void }) => {
  const [activeTab, setActiveTab] = useState<'summary' | 'risks' | 'chat'>('summary');
  const [question, setQuestion] = useState('');
  const [chatHistory, setChatHistory] = useState<{role: string, content: string}[]>([]);
  
  const { data: summary, isLoading: loadingSummary } = useQuery({
    queryKey: ['summary', contract.id],
    queryFn: () => fetchSummary(contract.id),
    enabled: activeTab === 'summary',
  });

  const { data: risksData, isLoading: loadingRisks } = useQuery({
    queryKey: ['risks', contract.id],
    queryFn: () => fetchRisks(contract.id),
    enabled: activeTab === 'risks',
  });

  const askMutation = useMutation({
    mutationFn: (q: string) => askQuestion(contract.id, q),
    onSuccess: (data, variables) => {
      setChatHistory(prev => [...prev, { role: 'user', content: variables }, { role: 'ai', content: data.answer }]);
      setQuestion('');
    }
  });

  const handleAsk = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    askMutation.mutate(question);
  };

  return (
    <div className="bg-surface-container-lowest rounded-xl shadow-2xl overflow-hidden border border-outline-variant/30 flex flex-col h-[700px]">
      {/* Header */}
      <div className="p-6 border-b border-outline-variant/20 flex justify-between items-center bg-surface-container-low">
        <div>
          <h2 className="text-xl font-bold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">description</span>
            {contract.filename}
          </h2>
          <p className="text-xs text-secondary mt-1">ID: {contract.id}</p>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-slate-200 dark:hover:bg-slate-800 rounded-full transition-colors">
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-outline-variant/20 bg-surface-container-low/50">
        {(['summary', 'risks', 'chat'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-3 text-sm font-bold capitalize transition-all ${activeTab === tab ? 'text-primary border-b-2 border-primary bg-primary/5' : 'text-secondary hover:text-on-surface'}`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* SUMMARY TAB */}
        {activeTab === 'summary' && (
          <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2">
            <h3 className="text-lg font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-xl">subject</span>
              AI Generated Summary
            </h3>
            {loadingSummary ? (
              <div className="animate-pulse space-y-3">
                <div className="h-4 bg-slate-200 rounded w-full"></div>
                <div className="h-4 bg-slate-200 rounded w-full"></div>
                <div className="h-4 bg-slate-200 rounded w-3/4"></div>
              </div>
            ) : (
              <div className="prose prose-slate dark:prose-invert max-w-none">
                <p className="text-on-surface leading-relaxed whitespace-pre-wrap">{summary}</p>
              </div>
            )}
          </div>
        )}

        {/* RISKS TAB */}
        {activeTab === 'risks' && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2">
            <div className="flex justify-between items-center bg-surface-container-low p-4 rounded-lg">
              <h3 className="text-lg font-bold text-on-surface flex items-center gap-2">
                <span className="material-symbols-outlined text-error text-xl">warning</span>
                Risk Analysis
              </h3>
              {risksData && (
                <div className="flex items-center gap-4">
                  <div className="text-center">
                    <span className="text-xs uppercase tracking-wider text-secondary font-bold block mb-1">Risk Score</span>
                    <span className={`text-2xl font-black ${risksData.risk_score > 60 ? 'text-error' : 'text-emerald-500'}`}>{risksData.risk_score}/100</span>
                  </div>
                </div>
              )}
            </div>

            {loadingRisks ? (
              <div className="animate-pulse space-y-4">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-24 bg-slate-100 rounded-lg"></div>
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                {risksData?.risks.length === 0 && <p className="text-secondary italic">No significant risks detected.</p>}
                {risksData?.risks.map((risk: any, i: number) => (
                  <div key={i} className="p-4 border border-error/20 bg-error/5 rounded-lg">
                    <div className="flex gap-2 items-start">
                      <span className="material-symbols-outlined text-error text-sm mt-0.5" style={{fontVariationSettings: "'FILL' 1"}}>error</span>
                      <div>
                        <h4 className="font-bold text-on-surface text-sm mb-1">{risk.issue_type || 'Potential Risk'}</h4>
                        <p className="text-on-surface text-sm">{risk.description}</p>
                        <div className="mt-3 p-3 bg-white/50 dark:bg-black/20 rounded text-xs font-mono text-secondary border border-outline-variant/30">
                          "{risk.clause_text}"
                        </div>
                        {risk.recommendation && (
                          <div className="mt-3 text-xs text-primary font-medium flex items-center gap-1">
                            <span className="material-symbols-outlined text-[14px]">lightbulb</span>
                            {risk.recommendation}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* CHAT TAB */}
        {activeTab === 'chat' && (
          <div className="flex flex-col h-full animate-in fade-in slide-in-from-bottom-2">
            <div className="flex-1 overflow-y-auto space-y-6 pb-4">
              {chatHistory.length === 0 && (
                <div className="text-center py-10 opacity-50">
                  <span className="material-symbols-outlined text-4xl mb-2">forum</span>
                  <p>Ask anything about this contract.</p>
                </div>
              )}
              {chatHistory.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl p-4 ${msg.role === 'user' ? 'bg-primary text-on-primary rounded-tr-sm' : 'bg-surface-container border border-outline-variant/30 rounded-tl-sm'}`}>
                    {msg.role === 'ai' && <div className="flex items-center gap-1.5 mb-1 text-xs font-bold text-primary opacity-80"><span className="material-symbols-outlined text-[14px]">smart_toy</span> ContractGuard AI</div>}
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              ))}
              {askMutation.isPending && (
                <div className="flex justify-start">
                  <div className="bg-surface-container border border-outline-variant/30 rounded-2xl rounded-tl-sm p-4 w-24">
                    <div className="flex gap-1 justify-center">
                      <span className="w-2 h-2 bg-primary rounded-full animate-bounce"></span>
                      <span className="w-2 h-2 bg-primary rounded-full animate-bounce delay-100"></span>
                      <span className="w-2 h-2 bg-primary rounded-full animate-bounce delay-200"></span>
                    </div>
                  </div>
                </div>
              )}
            </div>
            <form onSubmit={handleAsk} className="mt-auto relative">
              <input
                type="text"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                placeholder="E.g. What is the governing law in this MSA?"
                className="w-full bg-surface-container-low border border-outline-variant/50 rounded-full py-4 pl-6 pr-16 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary shadow-sm"
                disabled={askMutation.isPending}
              />
              <button 
                type="submit" 
                disabled={askMutation.isPending || !question.trim()}
                className="absolute right-2 top-2 bottom-2 w-10 bg-primary text-on-primary rounded-full flex items-center justify-center disabled:opacity-50 hover:bg-primary-container hover:text-on-primary-container transition-colors"
              >
                <span className="material-symbols-outlined text-sm">send</span>
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};

export const ContractsView = ({ contracts }: { contracts: Contract[] }) => {
  const [selectedContract, setSelectedContract] = useState<Contract | null>(null);

  const readyContracts = contracts.filter(c => c.status === 'ready');

  if (selectedContract) {
    return <DocumentDetail contract={selectedContract} onClose={() => setSelectedContract(null)} />;
  }

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h2 className="text-2xl font-bold text-on-background mb-2">Vault Explorer</h2>
          <p className="text-secondary text-sm">Select a processed document to analyze, summarize, or interrogate.</p>
        </div>
      </div>

      {readyContracts.length === 0 ? (
        <div className="bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-12 text-center">
          <span className="material-symbols-outlined text-4xl text-secondary mb-4">folder_off</span>
          <h3 className="text-lg font-bold">No Verified Contracts</h3>
          <p className="text-secondary mt-2">Upload contracts from the dashboard to populate your vault.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {readyContracts.map(contract => (
            <div 
              key={contract.id} 
              onClick={() => setSelectedContract(contract)}
              className="bg-surface-container-lowest p-6 rounded-xl border border-outline-variant/30 hover:border-primary/50 hover:shadow-xl hover:shadow-primary/5 transition-all cursor-pointer group flex flex-col"
            >
              <div className="flex justify-between items-start mb-4">
                <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center text-primary group-hover:scale-110 transition-transform">
                  <span className="material-symbols-outlined">description</span>
                </div>
                <span className="px-2.5 py-1 bg-emerald-50 text-emerald-600 rounded-md text-[10px] font-black uppercase tracking-widest">Verified</span>
              </div>
              <h4 className="font-bold text-on-surface line-clamp-2 leading-snug mb-2">{contract.filename}</h4>
              <div className="mt-auto pt-4 flex items-center justify-between text-xs text-secondary border-t border-outline-variant/20">
                <span className="flex items-center gap-1"><span className="material-symbols-outlined text-[14px]">calendar_today</span> {new Date(contract.uploadedAt || '').toLocaleDateString()}</span>
                <span className="text-primary font-bold opacity-0 group-hover:opacity-100 transition-opacity">Analyze →</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
