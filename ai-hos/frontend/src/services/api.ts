import axios from 'axios';
import type {
  ClinicalDocStats,
  PayerPolicy,
  PriorAuthDecision,
  PriorAuthRequest,
  PriorAuthStats,
  ServiceHealth,
  SOAPGenerationResponse,
  VoiceSession,
} from '../types/clinical';

export const CLINICAL_DOC_BASE_URL =
  import.meta.env.VITE_CLINICAL_API_URL || 'http://localhost:8000';
export const PRIOR_AUTH_BASE_URL =
  import.meta.env.VITE_PRIOR_AUTH_API_URL || 'http://localhost:8001';

export const CLINICAL_DOC_WS_URL = CLINICAL_DOC_BASE_URL.replace(/^http/, 'ws');

const docClient = axios.create({
  baseURL: CLINICAL_DOC_BASE_URL,
  timeout: 20000,
});

const authClient = axios.create({
  baseURL: PRIOR_AUTH_BASE_URL,
  timeout: 15000,
});

export const clinicalDocApi = {
  async health(): Promise<ServiceHealth> {
    const { data } = await docClient.get<ServiceHealth>('/health');
    return data;
  },

  async createSession(payload: {
    patient_id: string;
    provider_id: string;
    encounter_id?: string;
    chief_complaint?: string;
  }): Promise<VoiceSession> {
    const { data } = await docClient.post<VoiceSession>('/api/v1/sessions', payload);
    return data;
  },

  async listSessions(limit = 30): Promise<VoiceSession[]> {
    const { data } = await docClient.get<VoiceSession[]>('/api/v1/sessions', {
      params: { limit },
    });
    return data;
  },

  async getSession(sessionId: string): Promise<VoiceSession> {
    const { data } = await docClient.get<VoiceSession>(`/api/v1/sessions/${sessionId}`);
    return data;
  },

  async generateSoap(payload: {
    session_id: string;
    transcript: string;
    patient_context?: Record<string, unknown>;
  }): Promise<SOAPGenerationResponse> {
    const { data } = await docClient.post<SOAPGenerationResponse>(
      '/api/v1/generate-soap',
      payload
    );
    return data;
  },

  async updateSoap(
    sessionId: string,
    payload: {
      subjective: string;
      objective: string;
      assessment: string;
      plan: string;
      approved?: boolean;
      approved_by?: string;
    }
  ): Promise<VoiceSession> {
    const { data } = await docClient.put<VoiceSession>(
      `/api/v1/sessions/${sessionId}/soap`,
      payload
    );
    return data;
  },

  async exportFhir(sessionId: string): Promise<Record<string, unknown>> {
    const { data } = await docClient.get<Record<string, unknown>>(
      `/api/v1/sessions/${sessionId}/fhir`
    );
    return data;
  },

  async getStats(): Promise<ClinicalDocStats> {
    const { data } = await docClient.get<ClinicalDocStats>('/api/v1/stats');
    return data;
  },
};

export const priorAuthApi = {
  async health(): Promise<ServiceHealth> {
    const { data } = await authClient.get<ServiceHealth>('/health');
    return data;
  },

  async listPolicies(): Promise<PayerPolicy[]> {
    const { data } = await authClient.get<PayerPolicy[]>('/api/v1/prior-auth/policies');
    return data;
  },

  async createPolicy(policy: PayerPolicy): Promise<PayerPolicy> {
    const { data } = await authClient.post<PayerPolicy>(
      '/api/v1/prior-auth/policies',
      policy
    );
    return data;
  },

  async deletePolicy(policyId: string): Promise<void> {
    await authClient.delete(`/api/v1/prior-auth/policies/${policyId}`);
  },

  async evaluate(request: PriorAuthRequest): Promise<PriorAuthDecision> {
    const { data } = await authClient.post<PriorAuthDecision>(
      '/api/v1/prior-auth/evaluate',
      request
    );
    return data;
  },

  async listDecisions(limit = 30): Promise<PriorAuthDecision[]> {
    const { data } = await authClient.get<PriorAuthDecision[]>(
      '/api/v1/prior-auth/decisions',
      { params: { limit } }
    );
    return data;
  },

  async getStats(): Promise<PriorAuthStats> {
    const { data } = await authClient.get<PriorAuthStats>('/api/v1/prior-auth/stats');
    return data;
  },
};

export interface ClinicalSampleCase {
  id: string;
  label: string;
  specialty: string;
  patientId: string;
  age: number;
  gender: 'M' | 'F' | 'O';
  defaultPayer: string;
  chiefComplaint: string;
  transcript: string;
}

export const SAMPLE_CLINICAL_CASES: ClinicalSampleCase[] = [
  {
    id: 'ortho-knee-mri',
    label: 'Orthopedic Knee OA (MRI)',
    specialty: 'Orthopedics',
    patientId: 'PAT-1042',
    age: 68,
    gender: 'F',
    defaultPayer: 'UHC',
    chiefComplaint: 'Chronic left knee pain',
    transcript:
      'Patient: Jane Doe (MRN-884210, phone 555-234-8891) is a 68-year-old female presenting with severe chronic left knee pain and morning stiffness for 6 months. She failed conservative therapy including 8 weeks of physical therapy and ibuprofen 400 mg twice daily. Allergies: allergic to penicillin. Physical exam shows BP 136/84 mmHg, HR 76 bpm, mild joint swelling, medial joint-line tenderness, and crepitus with limited range of motion. Prior weight-bearing knee X-ray showed moderate medial compartment narrowing consistent with left knee osteoarthritis. Assessment: Left knee osteoarthritis refractory to conservative therapy. Plan: Order MRI of the left knee to evaluate meniscal integrity, start meloxicam 15 mg once daily, submit prior authorization to UHC, and follow up in 2 weeks.',
  },
  {
    id: 'cardio-chf-echo',
    label: 'Cardiology CHF (Echo)',
    specialty: 'Cardiology',
    patientId: 'PAT-2091',
    age: 72,
    gender: 'M',
    defaultPayer: 'UHC',
    chiefComplaint: 'Progressive dyspnea & leg swelling',
    transcript:
      '72-year-old male with history of hypertension, atrial fibrillation, and congestive heart failure presenting with worsening shortness of breath, orthopnea, and bilateral lower extremity edema over the past 3 weeks. No known drug allergies. Exam reveals BP 148/92 mmHg, HR 88 bpm, SpO2 94%, bibasilar crackles on lung auscultation, and 2+ ankle swelling. EKG showed controlled atrial fibrillation and elevated BNP. Plan: Order transthoracic echocardiogram to assess ejection fraction, increase furosemide 40 mg once daily, continue lisinopril 20 mg daily and apixaban 5 mg twice daily, follow up in cardiology clinic in 1 week.',
  },
  {
    id: 'pulm-copd-ct',
    label: 'Pulmonology COPD (Chest CT)',
    specialty: 'Pulmonology',
    patientId: 'PAT-3318',
    age: 64,
    gender: 'M',
    defaultPayer: 'BCBS',
    chiefComplaint: 'Persistent productive cough & wheezing',
    transcript:
      '64-year-old male with COPD presenting with persistent productive cough, wheezing, and worsening dyspnea for 4 weeks despite albuterol inhaler and prednisone taper. NKDA. Vitals: BP 132/80 mmHg, HR 90 bpm, Temp 99.2 F, SpO2 92%. Lung exam shows diffuse expiratory wheezes. Prior chest X-ray showed hyperinflation and subtle right lower lobe opacity. Assessment: Acute exacerbation of COPD with persistent opacity. Plan: Order diagnostic chest CT scan to rule out underlying parenchymal pathology, prescribe azithromycin 250 mg daily and tiotropium inhaler, follow up in 10 days.',
  },
  {
    id: 'spine-radic-mri',
    label: 'Neurology Lumbar Radiculopathy',
    specialty: 'Spine / Neurology',
    patientId: 'PAT-4110',
    age: 54,
    gender: 'F',
    defaultPayer: 'Aetna',
    chiefComplaint: 'Low back pain radiating to leg',
    transcript:
      '54-year-old female presenting with severe chronic low back pain radiating down the right leg with numbness and tingling for 10 weeks. Patient failed conservative management including 6 weeks of physical therapy, naproxen 500 mg twice daily, and gabapentin 300 mg at bedtime. Sulfa allergy documented. Exam: BP 124/78 mmHg, HR 72 bpm, positive right straight-leg raise and mild sensory deficit along L5 dermatome. Assessment: Lumbar radiculopathy refractory to conservative care. Plan: Order lumbar spine MRI without contrast, continue gabapentin, submit prior authorization to Aetna, and follow up after imaging.',
  },
];
