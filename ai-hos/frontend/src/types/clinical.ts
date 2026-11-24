export type EntityType =
  | 'diagnosis'
  | 'procedure'
  | 'medication'
  | 'symptom'
  | 'allergy'
  | 'vital';

export interface ClinicalEntity {
  text: string;
  entity_type: EntityType;
  start: number;
  end: number;
  confidence: number;
  icd10?: string | null;
  rxnorm?: string | null;
  cpt?: string | null;
  snomed?: string | null;
  dosage?: string | null;
}

export interface SOAPNote {
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  entities: ClinicalEntity[];
  confidence_score: number;
  generated_at?: string;
  model_used?: string;
  phi_redacted_count?: number;
  approved?: boolean;
  approved_at?: string | null;
  approved_by?: string | null;
}

export interface VoiceSession {
  session_id: string;
  patient_id: string;
  encounter_id?: string | null;
  provider_id: string;
  chief_complaint?: string | null;
  status: 'pending' | 'recording' | 'processing' | 'completed' | 'approved' | 'error';
  created_at: string;
  updated_at?: string | null;
  completed_at?: string | null;
  audio_duration_seconds?: number | null;
  transcript?: string | null;
  redacted_transcript?: string | null;
  soap_note?: SOAPNote | null;
}

export interface SOAPGenerationResponse {
  session_id: string;
  soap_note: SOAPNote;
  redacted_transcript: string;
  phi_redactions: string[];
  processing_time_ms: number;
  model_version: string;
}

export interface ClinicalDocStats {
  total_sessions: number;
  completed_sessions: number;
  approved_notes: number;
  avg_confidence: number;
  total_entities_extracted: number;
  entity_breakdown: Record<string, number>;
  storage_backend: string;
  llm_mode: string;
}

export interface PolicyRule {
  field: string;
  operator: 'eq' | 'ne' | 'gt' | 'lt' | 'gte' | 'lte' | 'in' | 'contains';
  value: unknown;
  weight: number;
  description?: string | null;
}

export interface MedicalNecessityCriteria {
  description: string;
  required_evidence: string[];
  duration_requirement?: string | null;
}

export interface PayerPolicy {
  policy_id: string;
  payer_id: string;
  payer_name: string;
  policy_title?: string | null;
  procedure_codes: string[];
  diagnosis_codes: string[];
  rules: PolicyRule[];
  medical_necessity?: MedicalNecessityCriteria | null;
  auto_approve_threshold: number;
  auto_deny_threshold: number;
  version: string;
  effective_date?: string;
}

export interface PriorAuthRequest {
  request_id: string;
  patient_id: string;
  provider_id: string;
  payer_id: string;
  procedure_code: string;
  diagnosis_codes: string[];
  patient_age: number;
  patient_gender: 'M' | 'F' | 'O';
  previous_procedures: string[];
  current_medications: string[];
  clinical_notes?: string;
  urgency: 'routine' | 'urgent' | 'emergent';
}

export interface RuleEvaluationDetail {
  rule: string;
  passed: boolean;
  score: number;
  weight: number;
  description?: string | null;
}

export interface PriorAuthDecision {
  request_id: string;
  payer_id?: string | null;
  procedure_code?: string | null;
  diagnosis_codes: string[];
  decision: 'auto_approve' | 'auto_deny' | 'escalate';
  confidence_score: number;
  rule_score?: number | null;
  medical_necessity_score?: number | null;
  matched_policy_id?: string | null;
  matched_policy_title?: string | null;
  matched_rules: string[];
  failed_rules: string[];
  rule_results: RuleEvaluationDetail[];
  reasoning: string;
  required_documents: string[];
  suggested_diagnosis_codes: string[];
  urgency_override: boolean;
  processed_at: string;
  estimated_decision_time_hours?: number | null;
}

export interface PriorAuthStats {
  total_policies: number;
  total_evaluations: number;
  auto_approved: number;
  auto_denied: number;
  escalated: number;
  auto_approval_rate: number;
  avg_confidence: number;
  payers: string[];
}

export interface ServiceHealth {
  status: string;
  service: string;
  version: string;
  [key: string]: unknown;
}
