# AI-HOS (AI Hospital Operating System) — What This Project Is & How to Run

## 1. What Is This Project About?

**AI-HOS (AI Hospital Operating System)** is a **HIPAA-aware clinical documentation and automated insurance prior authorization platform** designed for hospitals and clinics.

It automates the most time-consuming administrative workflow in healthcare:

```text
Doctor Voice / Clinical Encounter Transcript
        │
        ▼
[1] Clinical Documentation AI Service (FastAPI · Port 8000)
    • Real-time WebSocket dictation + REST API
    • HIPAA Safe Harbor PHI Redaction (SSN, phone, email, MRN, DOB, patient name)
    • Clinical Entity Extraction & Standardized Coding:
        - Diagnoses   → ICD-10-CM codes (e.g., M17.12 Left Knee Osteoarthritis)
        - Medications → RxNorm codes + dosage extraction (e.g., Ibuprofen 400 mg BID)
        - Procedures  → CPT codes (e.g., 73706 Knee MRI, 93306 Echocardiogram)
        - Symptoms, Allergies, and Vital Signs
    • Structured SOAP Note Generation (Subjective, Objective, Assessment, Plan)
    • HL7 FHIR R4 Document Bundle Export (Composition + Condition + MedicationRequest + ServiceRequest)
    • Persistent SQLite storage (or optional MongoDB)
        │
        ▼  (One-click handoff in UI)
[2] Prior Authorization Engine (FastAPI · Port 8001)
    • Forward-chaining payer policy rule engine with weighted rules
    • Clinical medical-necessity evidence analyzer (detects failed conservative therapy, duration, imaging)
    • Preloaded policies across UHC, Aetna, BCBS, Cigna, and CMS Medicare
    • Instant explainable decisions: AUTO APPROVE · ESCALATE · AUTO DENY
    • Audit trail & custom policy authoring
        │
        ▼
[3] Clinician Dashboard (React + TypeScript + Vite + Tailwind · Port 5173)
    • Live Voice Dictation & Transcript Editor with 4 realistic specialty sample cases
    • Interactive SOAP Note Editor, EHR Approval, & FHIR R4 JSON Exporter
    • Prior Authorization Workbench & Payer Policy Manager
    • Real-time Operations Analytics Dashboard (Recharts)
```

---

## 2. What Was Upgraded in v2.0

The original repository contained partially extracted blueprint files from `code.txt` that could not run out of the box. In v2.0, the entire project was repaired, modernized, and upgraded:

- **Fixed Corrupted Files**: Cleaned up parser-leaked prose and encoding artifacts in `SOAPDisplay.tsx`, `VoiceRecorder.tsx`, `prior-auth-engine/app/api/endpoints.py`, `docker-compose.services.yml`, and `01_fhir_schema.sql` (including fixing PostgreSQL range partitioning syntax).
- **Upgraded Clinical Documentation AI (`:8000`)**:
  - Modernized dependencies for Python 3.11–3.15 (`FastAPI`, `Pydantic v2`, `Uvicorn`, `OpenAI SDK`, `aiosqlite`).
  - Added real **HIPAA Safe Harbor PHI redaction** (`app/core/phi_redactor.py`).
  - Built a hybrid **Clinical NER + Coding engine** (`ICD-10-CM`, `RxNorm` + dosages, `CPT`, symptoms, allergies, vitals) that runs immediately with zero heavy GPU downloads, while still supporting optional `WhisperX` / `scispaCy` / `BioClinicalBERT` (`requirements-ml.txt`).
  - Added an intelligent **structured local SOAP synthesizer** plus optional OpenAI-compatible LLM integration (`Ollama` / `vLLM` / `OpenAI`).
  - Added **HL7 FHIR R4 Bundle export** (`/api/v1/sessions/{id}/fhir`), SOAP edit/approval persistence, and zero-config **SQLite persistence** (with optional MongoDB).
  - Fixed WebSocket JSON datetime serialization crashes and WebM/live-caption dictation handling.
- **Upgraded Prior Authorization Engine (`:8001`)**:
  - Created missing `app/main.py`, `Dockerfile`, and SQLite audit store.
  - **Fixed a critical math bug** in `rule_engine.py` where passing rules had their score divided by the number of rules (causing valid requests to fail) and removed an unused broken `numpy` import.
  - Added **7 preloaded payer policies** (`UHC`, `Aetna`, `BCBS`, `Cigna`, `Medicare`), transparent rule-by-rule pass/fail traces, medical necessity duration parsing, emergent urgency fast-tracking, and custom policy CRUD APIs.
- **Built Complete React + Vite Frontend (`:5173`)**:
  - Added missing Vite/TypeScript/Tailwind scaffolding (`index.html`, `vite.config.ts`, `tsconfig.json`, `App.tsx`, `main.tsx`, typed API layer).
  - Upgraded `VoiceRecorder` (Web Speech API live captions + WebSocket streaming) and `SOAPDisplay` (FHIR modal, EHR approval, one-click Prior Auth handoff).
  - Added `PriorAuthPanel`, `PoliciesPanel`, and `AnalyticsPanel` with live service heartbeat indicators.
- **Added Automated Test Suites**: `pytest` coverage for both microservices.

---

## 3. Prerequisites

- **Python 3.11+** (verified on Python 3.15)
- **Node.js 18+** & **npm** (verified on Node 26 / npm 11)
- *(Optional)* Docker Desktop & Ollama if you want to run containerized PostgreSQL/MongoDB/Local LLMs.

---

## 4. How to Run (Fastest Way — One Paste in Terminal!)

Simply paste this command into **PowerShell** or **Command Prompt** (or double-click `run.bat` in File Explorer):

```bat
D:\Projects\AI-HOS\run.bat
```

Or if your terminal is already inside `D:\Projects\AI-HOS`:

```bat
.\run.bat
```

### What `run.bat` Does Automatically
1. Verifies Python and Node.js are installed.
2. Creates a local Python virtual environment (`.venv`) and installs backend packages on the first run.
3. Installs frontend `node_modules` on the first run.
4. Starts all three services in separate titled windows:
   - **Frontend Clinician Dashboard**: http://localhost:5173
   - **Clinical Documentation AI (Swagger UI)**: http://localhost:8000/docs
   - **Prior Authorization Engine (Swagger UI)**: http://localhost:8001/docs
5. Automatically opens **http://localhost:5173** in your browser.

To stop all running services at once, paste:

```bat
D:\Projects\AI-HOS\stop.bat
```

---

## 5. How to Run Manually (Step by Step)

If you prefer running each service manually in separate terminals from `D:\Projects\AI-HOS`:

### Terminal 1 — Clinical Documentation AI (Port 8000)
```powershell
cd D:\Projects\AI-HOS\ai-hos\services\clinical-doc-ai
..\..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — Prior Authorization Engine (Port 8001)
```powershell
cd D:\Projects\AI-HOS\ai-hos\services\prior-auth-engine
..\..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Terminal 3 — React Frontend Dashboard (Port 5173)
```powershell
cd D:\Projects\AI-HOS\ai-hos\frontend
npm.cmd run dev
```

*(Note: On Windows where PowerShell script execution policy restricts `npm.ps1`, use `npm.cmd` in PowerShell or run inside `cmd.exe`.)*

---

## 6. Optional: Connecting a Local LLM (Ollama) or Docker Infrastructure

By default, AI-HOS runs in **fast zero-dependency local mode** using its built-in clinical NLP + structured SOAP engine and SQLite persistence.

To enable a live local LLM (e.g., Ollama with Llama 3.1):
1. Install Ollama and pull a model: `ollama pull llama3.1:8b`
2. Create `ai-hos/services/clinical-doc-ai/.env`:
   ```env
   ENABLE_LLM_GENERATION=true
   LLM_BASE_URL=http://localhost:11434/v1
   LLM_MODEL=llama3.1:8b
   ```
3. Restart the Clinical Doc AI service. If Ollama is unreachable, it automatically falls back to the local structured clinical engine.

For full Docker infrastructure (PostgreSQL FHIR DB, MongoDB, Redis, Ollama, MinIO):
```bash
docker compose -f ai-hos/infra/docker/docker-compose.infra.yml up -d
docker compose -f ai-hos/infra/docker/docker-compose.services.yml up --build
```

---

## 7. Running Automated Tests

From `D:\Projects\AI-HOS`:

```powershell
# Test Clinical Documentation AI
cd D:\Projects\AI-HOS\ai-hos\services\clinical-doc-ai
..\..\..\.venv\Scripts\python.exe -m pytest -v

# Test Prior Authorization Engine
cd D:\Projects\AI-HOS\ai-hos\services\prior-auth-engine
..\..\..\.venv\Scripts\python.exe -m pytest -v
```

---

## 8. Project Structure

```text
AI-HOS/
├── run.bat                              # One-click / one-paste launcher for Windows
├── stop.bat                             # Cleanly stops all 3 AI-HOS servers
├── WHAT_IS_THIS_AND_HOW_TO_RUN.md       # This guide
├── README.md                            # Quick project summary
└── ai-hos/
    ├── frontend/                        # React + TypeScript + Vite + Tailwind Dashboard
    │   └── src/
    │       ├── App.tsx                  # Main 4-tab hospital AI workspace
    │       ├── services/api.ts          # Typed API clients + sample specialty cases
    │       ├── types/clinical.ts        # Shared TypeScript interfaces
    │       └── components/
    │           ├── VoiceRecorder.tsx    # Live dictation + WebSocket audio streamer
    │           ├── SOAPDisplay.tsx      # SOAP editor, PHI shield, FHIR R4 export modal
    │           ├── PriorAuthPanel.tsx   # Prior auth evaluator + audit trail
    │           ├── PoliciesPanel.tsx    # Payer policy catalog + custom policy creator
    │           └── AnalyticsPanel.tsx   # Live KPI cards, Recharts charts, encounter list
    ├── services/
    │   ├── clinical-doc-ai/             # FastAPI Service (Port 8000)
    │   │   ├── app/core/                # ASR, Clinical NER, PHI Redactor, SOAP LLM, FHIR R4
    │   │   ├── app/db/mongodb.py        # Async SQLite (default) + optional MongoDB repo
    │   │   └── tests/                   # Pytest suite
    │   └── prior-auth-engine/           # FastAPI Service (Port 8001)
    │       ├── app/engine/rule_engine.py# Weighted rule + medical necessity engine
    │       ├── app/policies/            # 7 preloaded payer policies (UHC/Aetna/BCBS/Cigna/Medicare)
    │       ├── app/db/store.py          # Async SQLite persistence & audit store
    │       └── tests/                   # Pytest suite
    └── infra/
        ├── docker/                      # Fixed Docker Compose files
        └── postgres/init/               # Fixed FHIR R4 + partitioned HIPAA audit SQL schema
```

---

## 9. Quick Walkthrough Once Opened

1. Open **http://localhost:5173** and check that both top-right pills show green (`Doc AI :8000` and `Prior Auth :8001`).
2. In **Clinical Documentation**, click **Generate Coded SOAP Note** on the preloaded *Orthopedic Knee OA (MRI)* case (or pick another specialty sample or click the microphone to dictate live).
3. Inspect the **HIPAA Shield** badge (notice patient name, MRN, and phone were automatically redacted!), extracted **ICD-10 / CPT / RxNorm** badges, and 4-section **SOAP Note**.
4. Click **Export FHIR R4 Bundle** to view/download the HL7 FHIR JSON, or click **Approve & Save to EHR**.
5. Click **Send to Prior Authorization** to pre-fill the CPT/ICD-10 codes and clinical justification into the **Prior Authorization** tab, then hit **Run Automated Prior Authorization** to see instant policy evaluation!
