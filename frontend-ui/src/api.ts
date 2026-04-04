import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface Contract {
  id: string;
  filename: string;
  status: string;
  uploadedAt?: string;
}

export const fetchContracts = async (): Promise<Contract[]> => {
  const { data } = await api.get('/contracts');
  // Backend returns { contracts: [{ contract_id, title, uploaded_at }] }
  return data.contracts.map((c: any) => ({
    id: c.contract_id,
    filename: c.title || 'Untitled_Contract.txt',
    status: 'ready', // Initial assumption since list endpoint lacks status
    uploadedAt: c.uploaded_at
  }));
};

export const uploadContract = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return data;
};

export const fetchContractStatus = async (contractId: string) => {
  const { data } = await api.get(`/contracts/${contractId}/status`);
  return data;
};

export const fetchInsights = async (contractId: string) => {
  // First extract metadata
  const { data: metadata } = await api.post('/extract-metadata', { contract_id: contractId });
  // Then maybe get risks or summary
  const { data: risks } = await api.post('/risks', { contract_id: contractId, intensity: 'normal' });
  
  return { metadata: metadata.metadata, risks: risks.risks };
};

export const fetchSummary = async (contractId: string) => {
  const { data } = await api.post('/summary', { contract_id: contractId, max_chars: 800 });
  return data.summary;
};

export const fetchRisks = async (contractId: string) => {
  const { data } = await api.post('/risks', { contract_id: contractId });
  return data;
};

export const askQuestion = async (contractId: string, question: string, sessionId: string = '') => {
  const { data } = await api.post('/ask', { contract_id: contractId, question, session_id: sessionId });
  return data;
};

export const compareContracts = async (contractIdA: string, contractIdB: string) => {
  const { data } = await api.post('/compare', { contract_id_a: contractIdA, contract_id_b: contractIdB });
  return data;
};

export const clearSession = async () => {
  const { data } = await api.post('/clear');
  return data;
};

export default api;
