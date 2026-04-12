import axios from 'axios';

const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? '/api' : 'http://localhost:8000');

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Types ──────────────────────────────────────────────────────────

export interface Contract {
  id: string;
  filename: string;
  status: string;
  uploadedAt?: string;
}

export interface UploadResponse {
  contract_id: string;
  filename: string;
  text_preview: string;
  chunk_count: number;
  embedding_count: number;
  status: string;
}

export interface RiskItem {
  clause_type: string;
  title: string;
  severity: string;
  keyword: string;
  impact: number;
  evidence: string;
  explanation?: string;
  source?: string;
  source_url?: string;
}

export interface RisksResponse {
  contract_id: string;
  risk_score: number;
  safety_score: number;
  risk_level: string;
  detected_clause_count: number;
  risks: RiskItem[];
}

export interface MetadataField {
  value: string;
  confidence: number;
}

export interface MetadataResponse {
  contract_id: string;
  metadata: Record<string, MetadataField>;
}

export interface QAResponse {
  contract_id: string;
  question: string;
  answer: string;
  retrieved_chunks_count: number;
  session_id: string;
}

export interface CompareDetails {
  winner: string;
  contract_a_score: number;
  contract_b_score: number;
  summary?: string;
  risk_comparison: {
    contract_a_safety_score: number;
    contract_b_safety_score: number;
    contract_a_risk_score: number;
    contract_b_risk_score: number;
    contract_a_risk_level: string;
    contract_b_risk_level: string;
    contract_a_detected_clause_count: number;
    contract_b_detected_clause_count: number;
    safer_contract: string;
    safety_score_gap: number;
  };
  category_comparison: {
    key: string;
    label: string;
    contract_a_score: number;
    contract_b_score: number;
    better_contract: string;
    contract_a_verdict: string;
    contract_b_verdict: string;
    contract_a_evidence: string;
    contract_b_evidence: string;
  }[];
  key_differences: {
    dimension: string;
    better_contract: string;
    contract_a_evidence: string;
    contract_b_evidence: string;
    explanation?: string;
  }[];
}

export interface CompareResponse {
  contract_id_a: string;
  contract_id_b: string;
  summary: string;
  details: CompareDetails;
}

// ── API Functions ──────────────────────────────────────────────────

export const fetchContracts = async (): Promise<Contract[]> => {
  const { data } = await api.get('/contracts');
  return data.contracts.map((c: any) => ({
    id: c.contract_id,
    filename: c.title || 'Untitled_Contract.txt',
    status: 'ready',
    uploadedAt: c.uploaded_at,
  }));
};

export const uploadContract = async (file: File): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
};

export const ingestText = async (text: string, title: string): Promise<UploadResponse> => {
  const { data } = await api.post('/ingest-text', { text, title });
  return data;
};

export const fetchContractStatus = async (contractId: string) => {
  const { data } = await api.get(`/contracts/${contractId}/status`);
  return data;
};

export const fetchSummary = async (contractId: string): Promise<string> => {
  const { data } = await api.post('/summary', { contract_id: contractId, max_chars: 800 });
  return data.summary;
};

export const fetchRisks = async (contractId: string): Promise<RisksResponse> => {
  const { data } = await api.post('/risks', { contract_id: contractId });
  return data;
};

export const fetchMetadata = async (contractId: string): Promise<MetadataResponse> => {
  const { data } = await api.post('/extract-metadata', { contract_id: contractId });
  return data;
};

export const askQuestion = async (
  contractId: string,
  question: string,
  sessionId: string = ''
): Promise<QAResponse> => {
  const { data } = await api.post('/ask', {
    contract_id: contractId,
    question,
    session_id: sessionId,
    top_k: 4,
  });
  return data;
};

export const compareContracts = async (
  contractIdA: string,
  contractIdB: string
): Promise<CompareResponse> => {
  const { data } = await api.post('/compare', {
    contract_id_a: contractIdA,
    contract_id_b: contractIdB,
  });
  return data;
};

export const deleteContract = async (contractId: string) => {
  const { data } = await api.delete(`/contracts/${contractId}`);
  return data;
};

export const clearSession = async () => {
  const { data } = await api.post('/clear');
  return data;
};

// ── Vendor Verification ────────────────────────────────────────────

export interface VendorVerificationCheck {
  check: string;
  description: string;
  passed: boolean;
  points: number;
  max_points: number;
  detail: string;
}

export interface VendorVerification {
  contract_id: string;
  vendor_name: string;
  trust_score: number;
  trust_level: string;
  verification_mode: string;
  registry_data: Record<string, any>;
  red_flags: string[];
  checks: VendorVerificationCheck[];
  overall_assessment: string;
}

export const fetchVendorVerification = async (contractId: string): Promise<VendorVerification> => {
  const { data } = await api.post('/verify-vendor', { contract_id: contractId });
  return data;
};

// ── Zoho Sign ──────────────────────────────────────────────────────

export interface ZohoSigner {
  name: string;
  email: string;
  status: string;
  signedAt: string | null;
  ipAddress: string | null;
}

export interface ZohoSignatureResult {
  zohoStatus: string;
  isFullySigned: boolean;
  signers: ZohoSigner[];
  completedAt: string | null;
  expiresAt: string | null;
  documentName: string | null;
  auditTrailAvailable: boolean;
}

export interface ZohoAuditEvent {
  action: string;
  performedBy: string;
  performedAt: string | null;
  ipAddress: string | null;
}

export const fetchZohoStatus = async (): Promise<{ configured: boolean }> => {
  const { data } = await api.get('/zoho-status');
  return data;
};

export const verifyZohoSignature = async (requestId: string): Promise<ZohoSignatureResult> => {
  const { data } = await api.post('/verify-signature', { request_id: requestId });
  return data;
};

export const fetchZohoAuditTrail = async (requestId: string): Promise<{ request_id: string; events: ZohoAuditEvent[] }> => {
  const { data } = await api.post('/audit-trail', { request_id: requestId });
  return data;
};

export default api;
