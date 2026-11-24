/**
 * Prior Authorization Evaluator & Decision History Panel.
 */
import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  Play,
  Sparkles,
  Clock,
  FileCheck2,
} from 'lucide-react';
import { priorAuthApi } from '../services/api';
import type { PriorAuthDecision, PriorAuthRequest } from '../types/clinical';

interface PriorAuthPanelProps {
  prefill?: Partial<PriorAuthRequest> | null;
  onDecisionRecorded?: () => void;
}

const DEFAULT_FORM: PriorAuthRequest = {
  request_id: `PA-${Math.floor(1000 + Math.random() * 9000)}`,
  patient_id: 'PAT-1042',
  provider_id: 'PROV-001',
  payer_id: 'UHC',
  procedure_code: '73706',
  diagnosis_codes: ['M17.12'],
  patient_age: 68,
  patient_gender: 'F',
  previous_procedures: ['73560'],
  current_medications: ['ibuprofen', 'meloxicam'],
  clinical_notes:
    '68-year-old female with chronic left knee osteoarthritis pain for 6 months. Failed conservative therapy including 8 weeks of physical therapy and ibuprofen. Prior knee X-ray showed medial compartment narrowing.',
  urgency: 'routine',
};

export function PriorAuthPanel({ prefill, onDecisionRecorded }: PriorAuthPanelProps) {
  const [form, setForm] = useState<PriorAuthRequest>(DEFAULT_FORM);
  const [diagInput, setDiagInput] = useState(DEFAULT_FORM.diagnosis_codes.join(', '));
  const [medsInput, setMedsInput] = useState(DEFAULT_FORM.current_medications.join(', '));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decision, setDecision] = useState<PriorAuthDecision | null>(null);
  const [history, setHistory] = useState<PriorAuthDecision[]>([]);

  const loadHistory = async () => {
    try {
      const items = await priorAuthApi.listDecisions(15);
      setHistory(items);
    } catch {
      // Service might still be warming up
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    if (!prefill) return;
    setForm((prev) => {
      const merged: PriorAuthRequest = {
        ...prev,
        ...prefill,
        request_id: `PA-${Math.floor(1000 + Math.random() * 9000)}`,
      };
      setDiagInput((merged.diagnosis_codes || []).join(', '));
      setMedsInput((merged.current_medications || []).join(', '));
      return merged;
    });
  }, [prefill]);

  const applyPreset = (type: 'approve' | 'escalate' | 'deny') => {
    const reqId = `PA-${Math.floor(1000 + Math.random() * 9000)}`;
    if (type === 'approve') {
      const next: PriorAuthRequest = {
        ...DEFAULT_FORM,
        request_id: reqId,
      };
      setForm(next);
      setDiagInput(next.diagnosis_codes.join(', '));
      setMedsInput(next.current_medications.join(', '));
    } else if (type === 'escalate') {
      const next: PriorAuthRequest = {
        request_id: reqId,
        patient_id: 'PAT-2290',
        provider_id: 'PROV-001',
        payer_id: 'UHC',
        procedure_code: '73706',
        diagnosis_codes: ['M17.11'],
        patient_age: 42,
        patient_gender: 'M',
        previous_procedures: [],
        current_medications: [],
        clinical_notes: 'Mild knee discomfort noticed last week.',
        urgency: 'routine',
      };
      setForm(next);
      setDiagInput(next.diagnosis_codes.join(', '));
      setMedsInput('');
    } else {
      const next: PriorAuthRequest = {
        request_id: reqId,
        patient_id: 'PAT-3004',
        provider_id: 'PROV-001',
        payer_id: 'Cigna',
        procedure_code: '45378',
        diagnosis_codes: ['Z12.11'],
        patient_age: 26,
        patient_gender: 'F',
        previous_procedures: [],
        current_medications: [],
        clinical_notes: '',
        urgency: 'routine',
      };
      setForm(next);
      setDiagInput(next.diagnosis_codes.join(', '));
      setMedsInput('');
    }
  };

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload: PriorAuthRequest = {
        ...form,
        request_id: `PA-${Math.floor(1000 + Math.random() * 9000)}`,
        diagnosis_codes: diagInput
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        current_medications: medsInput
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const result = await priorAuthApi.evaluate(payload);
      setDecision(result);
      await loadHistory();
      onDecisionRecorded?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to reach Prior Authorization Engine (port 8001).'
      );
    } finally {
      setLoading(false);
    }
  };

  const decisionBadge = (d: PriorAuthDecision['decision']) => {
    if (d === 'auto_approve')
      return {
        label: 'AUTO APPROVED',
        bg: 'bg-emerald-50 border-emerald-200 text-emerald-900',
        pill: 'bg-emerald-600 text-white',
        icon: <CheckCircle2 className="w-6 h-6 text-emerald-600" />,
      };
    if (d === 'auto_deny')
      return {
        label: 'AUTO DENIED',
        bg: 'bg-rose-50 border-rose-200 text-rose-900',
        pill: 'bg-rose-600 text-white',
        icon: <XCircle className="w-6 h-6 text-rose-600" />,
      };
    return {
      label: 'ESCALATED FOR REVIEW',
      bg: 'bg-amber-50 border-amber-200 text-amber-900',
      pill: 'bg-amber-500 text-white',
      icon: <AlertTriangle className="w-6 h-6 text-amber-600" />,
    };
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Request Form */}
        <form
          onSubmit={handleEvaluate}
          className="lg:col-span-6 bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                Prior Authorization Request
              </h3>
              <p className="text-xs text-slate-500">
                Evaluate CPT + ICD-10 + clinical notes against payer rules in real time
              </p>
            </div>
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={() => applyPreset('approve')}
                className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
              >
                Auto-Approve Demo
              </button>
              <button
                type="button"
                onClick={() => applyPreset('escalate')}
                className="px-2.5 py-1 text-xs font-medium rounded-md bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200"
              >
                Escalate Demo
              </button>
              <button
                type="button"
                onClick={() => applyPreset('deny')}
                className="px-2.5 py-1 text-xs font-medium rounded-md bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200"
              >
                Auto-Deny Demo
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Payer</label>
              <select
                value={form.payer_id}
                onChange={(e) => setForm({ ...form, payer_id: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="UHC">UHC (UnitedHealthcare)</option>
                <option value="Aetna">Aetna Health</option>
                <option value="BCBS">BCBS (Blue Cross)</option>
                <option value="Cigna">Cigna Healthcare</option>
                <option value="Medicare">CMS Medicare</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">
                CPT Procedure Code
              </label>
              <input
                type="text"
                value={form.procedure_code}
                onChange={(e) => setForm({ ...form, procedure_code: e.target.value })}
                className="w-full px-3 py-2 text-sm font-mono border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="e.g. 73706"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Urgency</label>
              <select
                value={form.urgency}
                onChange={(e) =>
                  setForm({
                    ...form,
                    urgency: e.target.value as PriorAuthRequest['urgency'],
                  })
                }
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="routine">Routine</option>
                <option value="urgent">Urgent</option>
                <option value="emergent">Emergent (Fast-Track)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="col-span-2 sm:col-span-1">
              <label className="block text-xs font-medium text-slate-600 mb-1">
                ICD-10 Diagnoses
              </label>
              <input
                type="text"
                value={diagInput}
                onChange={(e) => setDiagInput(e.target.value)}
                className="w-full px-3 py-2 text-sm font-mono border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                placeholder="M17.11, M17.12"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">
                Patient Age
              </label>
              <input
                type="number"
                min={0}
                max={120}
                value={form.patient_age}
                onChange={(e) =>
                  setForm({ ...form, patient_age: Number(e.target.value) })
                }
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Gender</label>
              <select
                value={form.patient_gender}
                onChange={(e) =>
                  setForm({
                    ...form,
                    patient_gender: e.target.value as 'M' | 'F' | 'O',
                  })
                }
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                <option value="F">Female (F)</option>
                <option value="M">Male (M)</option>
                <option value="O">Other (O)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Current Medications (comma-separated)
            </label>
            <input
              type="text"
              value={medsInput}
              onChange={(e) => setMedsInput(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="ibuprofen, meloxicam"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Clinical Medical Necessity Notes
            </label>
            <textarea
              rows={4}
              value={form.clinical_notes || ''}
              onChange={(e) => setForm({ ...form, clinical_notes: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              placeholder="Document failed conservative therapy, duration, prior imaging, or symptoms..."
            />
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition-colors disabled:opacity-50"
          >
            <Play className="w-4 h-4 fill-white" />
            {loading ? 'Evaluating Policy Rules...' : 'Run Automated Prior Authorization'}
          </button>
        </form>

        {/* Decision Output */}
        <div className="lg:col-span-6 space-y-4">
          {decision ? (
            (() => {
              const style = decisionBadge(decision.decision);
              const pct = Math.round(decision.confidence_score * 100);
              return (
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-5">
                  <div className={`p-4 rounded-xl border flex items-center justify-between gap-4 ${style.bg}`}>
                    <div className="flex items-center gap-3">
                      {style.icon}
                      <div>
                        <span className={`inline-block px-2.5 py-0.5 text-xs font-bold rounded-full ${style.pill}`}>
                          {style.label}
                        </span>
                        <p className="text-sm font-semibold mt-1">
                          {decision.matched_policy_title || 'No Matching Payer Policy'}
                        </p>
                        {decision.matched_policy_id && (
                          <p className="text-xs opacity-75 font-mono">
                            Policy ID: {decision.matched_policy_id}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-3xl font-bold">{pct}%</p>
                      <p className="text-xs opacity-75">Decision Score</p>
                    </div>
                  </div>

                  {/* Score Breakdown */}
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <p className="text-xs text-slate-500">Policy Rules</p>
                      <p className="text-lg font-bold text-slate-900">
                        {decision.rule_score != null
                          ? `${Math.round(decision.rule_score * 100)}%`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <p className="text-xs text-slate-500">Medical Necessity</p>
                      <p className="text-lg font-bold text-slate-900">
                        {decision.medical_necessity_score != null
                          ? `${Math.round(decision.medical_necessity_score * 100)}%`
                          : 'N/A'}
                      </p>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                      <p className="text-xs text-slate-500">Turnaround</p>
                      <p className="text-lg font-bold text-slate-900 flex items-center justify-center gap-1">
                        <Clock className="w-4 h-4 text-slate-400" />
                        {decision.estimated_decision_time_hours === 0
                          ? 'Instant'
                          : `${decision.estimated_decision_time_hours}h`}
                      </p>
                    </div>
                  </div>

                  {/* Rule-by-rule trace */}
                  {decision.rule_results.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                        Rule-by-Rule Evaluation Trace
                      </h4>
                      <div className="space-y-1.5">
                        {decision.rule_results.map((r, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-xs"
                          >
                            <div className="flex items-center gap-2">
                              {r.passed ? (
                                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                              ) : (
                                <XCircle className="w-4 h-4 text-rose-600 shrink-0" />
                              )}
                              <span className="font-medium text-slate-800">
                                {r.description || r.rule}
                              </span>
                            </div>
                            <span className="font-mono text-slate-500">
                              wt {r.weight} · {r.passed ? 'PASS' : 'FAIL'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Reasoning */}
                  <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                      Explainable Reasoning
                    </h4>
                    <p className="text-xs text-slate-700 leading-relaxed">
                      {decision.reasoning}
                    </p>
                  </div>

                  {/* Required documents / suggestions for escalations */}
                  {decision.required_documents.length > 0 && (
                    <div className="p-3.5 rounded-lg bg-amber-50/70 border border-amber-200">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-amber-800 mb-1.5 flex items-center gap-1.5">
                        <FileCheck2 className="w-4 h-4" /> Required Documentation for Approval
                      </h4>
                      <ul className="list-disc list-inside text-xs text-amber-900 space-y-1">
                        {decision.required_documents.map((doc, idx) => (
                          <li key={idx}>{doc}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {decision.suggested_diagnosis_codes.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-slate-600">
                        Covered ICD-10 Suggestions:
                      </span>
                      {decision.suggested_diagnosis_codes.map((code) => (
                        <button
                          key={code}
                          type="button"
                          onClick={() => setDiagInput(code)}
                          className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 text-xs font-mono hover:bg-blue-100"
                        >
                          {code}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })()
          ) : (
            <div className="bg-white rounded-xl border border-dashed border-slate-300 p-10 text-center flex flex-col items-center justify-center min-h-[360px]">
              <Sparkles className="w-10 h-10 text-indigo-400 mb-3" />
              <h4 className="text-base font-semibold text-slate-800">
                Ready to Evaluate Prior Authorization
              </h4>
              <p className="text-sm text-slate-500 max-w-md mt-1">
                Submit the form on the left — or click <strong>Send to Prior Authorization</strong> directly from any generated SOAP note — to see instant payer policy matching and explainable medical-necessity scoring.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Decision Audit History */}
      {history.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-5 py-3.5 border-b border-slate-100 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-slate-500" />
            <h4 className="text-sm font-semibold text-slate-900">
              Recent Prior Authorization Audit Trail ({history.length})
            </h4>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 uppercase">
                <tr>
                  <th className="px-4 py-2.5">Request ID</th>
                  <th className="px-4 py-2.5">Payer</th>
                  <th className="px-4 py-2.5">CPT</th>
                  <th className="px-4 py-2.5">ICD-10</th>
                  <th className="px-4 py-2.5">Decision</th>
                  <th className="px-4 py-2.5">Score</th>
                  <th className="px-4 py-2.5">Matched Policy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {history.map((item, idx) => (
                  <tr
                    key={`${item.request_id}-${idx}`}
                    onClick={() => setDecision(item)}
                    className="hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="px-4 py-2.5 font-mono font-medium text-slate-800">
                      {item.request_id}
                    </td>
                    <td className="px-4 py-2.5">{item.payer_id || '-'}</td>
                    <td className="px-4 py-2.5 font-mono">{item.procedure_code || '-'}</td>
                    <td className="px-4 py-2.5 font-mono">
                      {item.diagnosis_codes.join(', ') || '-'}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded-full font-semibold ${
                          item.decision === 'auto_approve'
                            ? 'bg-emerald-100 text-emerald-800'
                            : item.decision === 'auto_deny'
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {item.decision.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-semibold">
                      {Math.round(item.confidence_score * 100)}%
                    </td>
                    <td className="px-4 py-2.5 font-mono text-slate-600">
                      {item.matched_policy_id || 'Unmatched'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
