-- FHIR R4 compatible schema for AI-HOS
-- HIPAA-compliant audit logging

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Patients table (de-identified for analytics)
CREATE TABLE patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fhir_id VARCHAR(64) UNIQUE NOT NULL,
    -- Pseudonymized identifiers
    mrn_hash VARCHAR(64) NOT NULL,
    -- Demographics (for analytics)
    birth_year INTEGER CHECK (birth_year > 1900 AND birth_year < 2100),
    gender VARCHAR(10) CHECK (gender IN ('male', 'female', 'other', 'unknown')),
    zip3 VARCHAR(3), -- First 3 digits of ZIP for geographic analysis
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Consent flags
    consent_research BOOLEAN DEFAULT FALSE,
    consent_sharing BOOLEAN DEFAULT FALSE
);

-- Encounters/Visits
CREATE TABLE encounters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fhir_id VARCHAR(64) UNIQUE NOT NULL,
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    encounter_type VARCHAR(50), -- ambulatory, emergency, inpatient
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    provider_id VARCHAR(64),
    department VARCHAR(100),
    -- For readmission prediction
    discharge_disposition VARCHAR(50),
    length_of_stay_hours INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Prior Authorization Requests
CREATE TABLE prior_auth_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(64) UNIQUE NOT NULL,
    patient_id UUID REFERENCES patients(id),
    provider_id VARCHAR(64) NOT NULL,
    payer_id VARCHAR(50) NOT NULL,
    -- Clinical
    procedure_code VARCHAR(20) NOT NULL,
    procedure_description TEXT,
    diagnosis_codes TEXT[], -- Array of ICD-10
    -- Decision
    decision VARCHAR(20) CHECK (decision IN ('auto_approve', 'auto_deny', 'escalate', 'manual_approve', 'manual_deny')),
    confidence_score DECIMAL(3,2),
    matched_policy_id VARCHAR(64),
    -- Timing
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    decided_at TIMESTAMP WITH TIME ZONE,
    decision_reasoning TEXT,
    -- Audit
    processed_by VARCHAR(64), -- AI service or user ID
    escalation_reason TEXT
);

-- Audit logs (HIPAA requirement)
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_id VARCHAR(64) NOT NULL,
    user_role VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL, -- CREATE, READ, UPDATE, DELETE
    resource_type VARCHAR(50) NOT NULL, -- Patient, Encounter, etc.
    resource_id VARCHAR(64) NOT NULL,
    purpose_of_use VARCHAR(50), -- TREATMENT, RESEARCH, PAYMENT
    consent_verified BOOLEAN DEFAULT FALSE,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    -- For detailed tracking
    request_payload JSONB,
    changes_made JSONB
);

-- Indexes for performance
CREATE INDEX idx_patients_mrn_hash ON patients(mrn_hash);
CREATE INDEX idx_encounters_patient ON encounters(patient_id);
CREATE INDEX idx_encounters_start ON encounters(start_time);
CREATE INDEX idx_prior_auth_patient ON prior_auth_requests(patient_id);
CREATE INDEX idx_prior_auth_decision ON prior_auth_requests(decision);
CREATE INDEX idx_audit_user ON audit_logs(user_id, timestamp);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);

-- Partition audit logs by month (for performance at scale)
CREATE TABLE audit_logs_2024_01 PARTITION OF audit_logs
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_patients_updated_at BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
6. Quick Start Guide
