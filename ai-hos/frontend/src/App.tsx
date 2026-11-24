import { useCallback, useEffect, useState } from 'react';
import {
  Stethoscope,
  ShieldCheck,
  BookOpen,
  BarChart3,
  Sparkles,
  FileAudio,
  Activity,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { VoiceRecorder } from './components/VoiceRecorder';
import { SOAPDisplay } from './components/SOAPDisplay';
import { PriorAuthPanel } from './components/PriorAuthPanel';
import { PoliciesPanel } from './components/PoliciesPanel';
import { AnalyticsPanel } from './components/AnalyticsPanel';
import {
  clinicalDocApi,
  priorAuthApi,
  SAMPLE_CLINICAL_CASES,
  type ClinicalSampleCase,
} from './services/api';
import type {
  ClinicalDocStats,
  PriorAuthRequest,
  PriorAuthStats,
  SOAPNote,
  VoiceSession,
} from './types/clinical';

type TabKey = 'documentation' | 'prior-auth' | 'policies' | 'analytics';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('documentation');

  // Service health
  const [docOnline, setDocOnline] = useState<boolean | null>(null);
  const [authOnline, setAuthOnline] = useState<boolean | null>(null);

  // Active clinical encounter state
  const [patientId, setPatientId] = useState('PAT-1042');
  const [providerId, setProviderId] = useState('PROV-001');
  const [patientAge, setPatientAge] = useState(68);
  const [patientGender, setPatientGender] = useState<'M' | 'F' | 'O'>('F');
  const [defaultPayer, setDefaultPayer] = useState('UHC');

  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());
  const [transcript, setTranscript] = useState(SAMPLE_CLINICAL_CASES[0].transcript);
  const [soapNote, setSoapNote] = useState<SOAPNote | null>(null);
  const [phiRedactions, setPhiRedactions] = useState<string[]>([]);
  const [generating, setGenerating] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Prior auth handoff
  const [priorAuthPrefill, setPriorAuthPrefill] =
    useState<Partial<PriorAuthRequest> | null>(null);

  // Analytics & history
  const [docStats, setDocStats] = useState<ClinicalDocStats | null>(null);
  const [authStats, setAuthStats] = useState<PriorAuthStats | null>(null);
  const [sessions, setSessions] = useState<VoiceSession[]>([]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const refreshSystemState = useCallback(async () => {
    try {
      await clinicalDocApi.health();
      setDocOnline(true);
      const [stats, list] = await Promise.all([
        clinicalDocApi.getStats(),
        clinicalDocApi.listSessions(25),
      ]);
      setDocStats(stats);
      setSessions(list);
    } catch {
      setDocOnline(false);
    }

    try {
      await priorAuthApi.health();
      setAuthOnline(true);
      const aStats = await priorAuthApi.getStats();
      setAuthStats(aStats);
    } catch {
      setAuthOnline(false);
    }
  }, []);

  useEffect(() => {
    refreshSystemState();
    const timer = setInterval(refreshSystemState, 15000);
    return () => clearInterval(timer);
  }, [refreshSystemState]);

  const loadSampleCase = (sample: ClinicalSampleCase) => {
    setPatientId(sample.patientId);
    setPatientAge(sample.age);
    setPatientGender(sample.gender);
    setDefaultPayer(sample.defaultPayer);
    setTranscript(sample.transcript);
    setSessionId(crypto.randomUUID());
    setSoapNote(null);
    setPhiRedactions([]);
    setDocError(null);
  };

  const handleGenerateSoap = async () => {
    if (!transcript.trim()) return;
    setGenerating(true);
    setDocError(null);
    try {
      const created = await clinicalDocApi.createSession({
        patient_id: patientId,
        provider_id: providerId,
      });
      setSessionId(created.session_id);

      const res = await clinicalDocApi.generateSoap({
        session_id: created.session_id,
        transcript,
        patient_context: { age: patientAge, gender: patientGender },
      });
      setSoapNote(res.soap_note);
      setPhiRedactions(res.phi_redactions);
      showToast(`SOAP note generated in ${res.processing_time_ms}ms`);
      refreshSystemState();
    } catch (err) {
      setDocError(
        err instanceof Error
          ? err.message
          : 'Failed to reach Clinical Documentation AI service (port 8000).'
      );
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveOrApproveSoap = async (updated: SOAPNote, approve = false) => {
    const saved = await clinicalDocApi.updateSoap(sessionId, {
      subjective: updated.subjective,
      objective: updated.objective,
      assessment: updated.assessment,
      plan: updated.plan,
      approved: approve || updated.approved,
      approved_by: providerId,
    });
    if (saved.soap_note) {
      setSoapNote(saved.soap_note);
    }
    showToast(approve ? 'SOAP note approved & signed to EHR!' : 'SOAP note changes saved.');
    refreshSystemState();
  };

  const handleSendToPriorAuth = (note: SOAPNote) => {
    const firstProcedure = note.entities.find(
      (e) => e.entity_type === 'procedure' && e.cpt
    );
    const diagnoses = note.entities
      .filter((e) => e.entity_type === 'diagnosis' && e.icd10)
      .map((e) => e.icd10 as string);
    const meds = note.entities
      .filter((e) => e.entity_type === 'medication')
      .map((e) => e.text);

    setPriorAuthPrefill({
      patient_id: patientId,
      provider_id: providerId,
      payer_id: defaultPayer,
      procedure_code: firstProcedure?.cpt || '73706',
      diagnosis_codes: diagnoses.length > 0 ? diagnoses : ['M17.11'],
      patient_age: patientAge,
      patient_gender: patientGender,
      current_medications: meds,
      clinical_notes: `${note.subjective}\n${note.assessment}`,
      urgency: 'routine',
    });
    setActiveTab('prior-auth');
    showToast('Pre-filled Prior Authorization request from SOAP note.');
  };

  const handleOpenSession = (sess: VoiceSession) => {
    setSessionId(sess.session_id);
    setPatientId(sess.patient_id);
    setProviderId(sess.provider_id);
    setTranscript(sess.transcript || '');
    setSoapNote(sess.soap_note || null);
    setActiveTab('documentation');
  };

  const navItems: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    {
      key: 'documentation',
      label: 'Clinical Documentation',
      icon: <FileAudio className="w-4 h-4" />,
    },
    {
      key: 'prior-auth',
      label: 'Prior Authorization',
      icon: <ShieldCheck className="w-4 h-4" />,
    },
    {
      key: 'policies',
      label: 'Payer Policies',
      icon: <BookOpen className="w-4 h-4" />,
    },
    {
      key: 'analytics',
      label: 'Analytics & Encounters',
      icon: <BarChart3 className="w-4 h-4" />,
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top Clinical Navigation Bar */}
      <header className="sticky top-0 z-30 bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white shadow-sm">
              <Stethoscope className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold text-slate-900 tracking-tight">
                  AI-HOS
                </h1>
                <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  v2.0
                </span>
              </div>
              <p className="text-xs text-slate-500 hidden sm:block">
                AI Hospital Operating System · Clinical Doc AI & Prior Auth
              </p>
            </div>
          </div>

          {/* Live Microservice Heartbeats */}
          <div className="flex items-center gap-2">
            <div
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                docOnline
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  docOnline ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
              Doc AI :8000
            </div>
            <div
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
                authOnline
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  authOnline ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
              Prior Auth :8001
            </div>
          </div>
        </div>

        {/* Tab Bar */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex gap-1 overflow-x-auto border-t border-slate-100">
          {navItems.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`inline-flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                activeTab === tab.key
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 space-y-6">
        {toast && (
          <div className="fixed bottom-5 right-5 z-50 flex items-center gap-2 px-4 py-3 rounded-xl bg-slate-900 text-white text-sm shadow-lg">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            {toast}
          </div>
        )}

        {activeTab === 'documentation' && (
          <div className="space-y-6">
            {/* Encounter Header + Sample Cases */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-blue-600" />
                  <h2 className="text-sm font-semibold text-slate-900">
                    Active Patient Encounter
                  </h2>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-slate-500 mr-1">Sample Cases:</span>
                  {SAMPLE_CLINICAL_CASES.map((sample) => (
                    <button
                      key={sample.id}
                      type="button"
                      onClick={() => loadSampleCase(sample)}
                      className="px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-slate-700 transition-colors"
                    >
                      {sample.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">
                    Patient ID
                  </label>
                  <input
                    value={patientId}
                    onChange={(e) => setPatientId(e.target.value)}
                    className="w-full px-3 py-1.5 text-sm font-mono border border-slate-300 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">
                    Provider ID
                  </label>
                  <input
                    value={providerId}
                    onChange={(e) => setProviderId(e.target.value)}
                    className="w-full px-3 py-1.5 text-sm font-mono border border-slate-300 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">
                    Age
                  </label>
                  <input
                    type="number"
                    value={patientAge}
                    onChange={(e) => setPatientAge(Number(e.target.value))}
                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">
                    Gender
                  </label>
                  <select
                    value={patientGender}
                    onChange={(e) =>
                      setPatientGender(e.target.value as 'M' | 'F' | 'O')
                    }
                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-lg bg-white"
                  >
                    <option value="F">Female</option>
                    <option value="M">Male</option>
                    <option value="O">Other</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">
                    Insurance Payer
                  </label>
                  <select
                    value={defaultPayer}
                    onChange={(e) => setDefaultPayer(e.target.value)}
                    className="w-full px-3 py-1.5 text-sm border border-slate-300 rounded-lg bg-white"
                  >
                    <option value="UHC">UHC</option>
                    <option value="Aetna">Aetna</option>
                    <option value="BCBS">BCBS</option>
                    <option value="Cigna">Cigna</option>
                    <option value="Medicare">Medicare</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Real-time Voice Recorder */}
            <VoiceRecorder
              sessionId={sessionId}
              onTranscript={(text, redactions) => {
                setTranscript(text);
                if (redactions) setPhiRedactions(redactions);
              }}
              onSoapNote={(note) => {
                setSoapNote(note);
                refreshSystemState();
              }}
            />

            {/* Dictation / Transcript Editor */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-semibold text-slate-900">
                  Clinical Encounter Transcript (HIPAA PHI auto-redacted)
                </label>
                <span className="text-xs text-slate-400">
                  {transcript.trim().split(/\s+/).filter(Boolean).length} words
                </span>
              </div>
              <textarea
                rows={5}
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                className="w-full p-3 text-sm text-slate-800 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none leading-relaxed"
                placeholder="Dictate or paste doctor-patient clinical conversation..."
              />
              {docError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" /> {docError}
                </div>
              )}
              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={generating || !transcript.trim()}
                  onClick={handleGenerateSoap}
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors disabled:opacity-50"
                >
                  <Sparkles className="w-4 h-4" />
                  {generating
                    ? 'Extracting Codes & Generating SOAP...'
                    : 'Generate Coded SOAP Note'}
                </button>
              </div>
            </div>

            {/* Generated SOAP Display */}
            {soapNote && (
              <SOAPDisplay
                sessionId={sessionId}
                note={soapNote}
                phiRedactions={phiRedactions}
                onSave={handleSaveOrApproveSoap}
                onExportFhir={() => clinicalDocApi.exportFhir(sessionId)}
                onSendToPriorAuth={handleSendToPriorAuth}
              />
            )}
          </div>
        )}

        {activeTab === 'prior-auth' && (
          <PriorAuthPanel
            prefill={priorAuthPrefill}
            onDecisionRecorded={refreshSystemState}
          />
        )}

        {activeTab === 'policies' && <PoliciesPanel />}

        {activeTab === 'analytics' && (
          <AnalyticsPanel
            docStats={docStats}
            authStats={authStats}
            sessions={sessions}
            onOpenSession={handleOpenSession}
            onRefresh={refreshSystemState}
          />
        )}
      </main>
    </div>
  );
}
