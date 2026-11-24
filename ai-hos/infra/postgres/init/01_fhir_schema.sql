-- FHIR R4 compatible schema for AI-HOS (v2.0)
-- HIPAA-compliant audit logging with valid range partitioning

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Patients table (pseudonymized for analytics)
CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fhir_id VARCHAR(64) UNIQUE NOT NULL,
    mrn_hash VARCHAR(64) NOT NULL,
    birth_year INTEGER CHECK (birth_year > 1900 AND birth_year < 2100),
    gender VARCHAR(10) CHECK (gender IN ('male', 'female', 'other', 'unknown')),
    zip3 VARCHAR(3),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    consent_research BOOLEAN DEFAULT FALSE,
    consent_sharing BOOLEAN DEFAULT FALSE
);

-- Encounters / Visits
CREATE TABLE IF NOT EXISTS encounters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fhir_id VARCHAR(64) UNIQUE NOT NULL,
    patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
    encounter_type VARCHAR(50),
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    provider_id VARCHAR(64),
    department VARCHAR(100),
    discharge_disposition VARCHAR(50),
    length_of_stay_hours INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Prior Authorization Requests
CREATE TABLE IF NOT EXISTS prior_auth_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id VARCHAR(64) UNIQUE NOT NULL,
    patient_id UUID REFERENCES patients(id),
    provider_id VARCHAR(64) NOT NULL,
    payer_id VARCHAR(50) NOT NULL,
    procedure_code VARCHAR(20) NOT NULL,
    procedure_description TEXT,
    diagnosis_codes TEXT[],
    decision VARCHAR(20) CHECK (
        decision IN ('auto_approve', 'auto_deny', 'escalate', 'manual_approve', 'manual_deny')
    ),
    confidence_score DECIMAL(4, 3),
    matched_policy_id VARCHAR(64),
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    decided_at TIMESTAMP WITH TIME ZONE,
    decision_reasoning TEXT,
    processed_by VARCHAR(64),
    escalation_reason TEXT
);

-- Partitioned HIPAA Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID DEFAULT uuid_generate_v4(),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    user_id VARCHAR(64) NOT NULL,
    user_role VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(64) NOT NULL,
    purpose_of_use VARCHAR(50),
    consent_verified BOOLEAN DEFAULT FALSE,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    request_payload JSONB,
    changes_made JSONB,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

CREATE TABLE IF NOT EXISTS audit_logs_2026 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS audit_logs_default PARTITION OF audit_logs DEFAULT;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_patients_mrn_hash ON patients(mrn_hash);
CREATE INDEX IF NOT EXISTS idx_encounters_patient ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_encounters_start ON encounters(start_time);
CREATE INDEX IF NOT EXISTS idx_prior_auth_patient ON prior_auth_requests(patient_id);
CREATE INDEX IF NOT EXISTS idx_prior_auth_decision ON prior_auth_requests(decision);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type, resource_id);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_patients_updated_at ON patients;
CREATE TRIGGER update_patients_updated_at
    BEFORE UPDATE ON patients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
