/**
 * Payer Policies Catalog & Live Policy Authoring Panel.
 */
import { useEffect, useState } from 'react';
import { BookOpen, Plus, Trash2, CheckCircle2 } from 'lucide-react';
import { priorAuthApi } from '../services/api';
import type { PayerPolicy } from '../types/clinical';

export function PoliciesPanel() {
  const [policies, setPolicies] = useState<PayerPolicy[]>([]);
  const [selectedPayer, setSelectedPayer] = useState<string>('ALL');
  const [showCreate, setShowCreate] = useState(false);
  const [policyId, setPolicyId] = useState('UHC-CUSTOM-001');
  const [payerId, setPayerId] = useState('UHC');
  const [payerName, setPayerName] = useState('UnitedHealthcare');
  const [title, setTitle] = useState('Diagnostic Abdominal CT (CPT 74150)');
  const [cptCodes, setCptCodes] = useState('74150');
  const [icdCodes, setIcdCodes] = useState('K80.20, K21.9');
  const [minAge, setMinAge] = useState(18);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const loadPolicies = async () => {
    try {
      const list = await priorAuthApi.listPolicies();
      setPolicies(list);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadPolicies();
  }, []);

  const payers = ['ALL', ...Array.from(new Set(policies.map((p) => p.payer_id))).sort()];
  const filtered =
    selectedPayer === 'ALL'
      ? policies
      : policies.filter((p) => p.payer_id === selectedPayer);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const newPolicy: PayerPolicy = {
      policy_id: policyId.trim(),
      payer_id: payerId.trim(),
      payer_name: payerName.trim(),
      policy_title: title.trim(),
      procedure_codes: cptCodes.split(',').map((s) => s.trim()).filter(Boolean),
      diagnosis_codes: icdCodes.split(',').map((s) => s.trim()).filter(Boolean),
      rules: [
        {
          field: 'age',
          operator: 'gte',
          value: minAge,
          weight: 1.0,
          description: `Patient age >= ${minAge}`,
        },
        {
          field: 'procedure_code',
          operator: 'in',
          value: cptCodes.split(',').map((s) => s.trim()).filter(Boolean),
          weight: 1.5,
          description: 'Covered CPT code',
        },
      ],
      medical_necessity: {
        description: 'Documented clinical symptoms or prior diagnostic workup.',
        required_evidence: ['Clinical progress note', 'Relevant diagnostic history'],
      },
      auto_approve_threshold: 0.78,
      auto_deny_threshold: 0.35,
      version: '2.0',
    };
    await priorAuthApi.createPolicy(newPolicy);
    await loadPolicies();
    setShowCreate(false);
    setStatusMsg(`Saved policy ${newPolicy.policy_id}`);
    setTimeout(() => setStatusMsg(null), 3000);
  };

  const handleDelete = async (id: string) => {
    await priorAuthApi.deletePolicy(id);
    await loadPolicies();
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {payers.map((payer) => (
            <button
              key={payer}
              type="button"
              onClick={() => setSelectedPayer(payer)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                selectedPayer === payer
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
              }`}
            >
              {payer}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setShowCreate((v) => !v)}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm"
        >
          <Plus className="w-4 h-4" /> Add Payer Policy
        </button>
      </div>

      {statusMsg && (
        <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" /> {statusMsg}
        </div>
      )}

      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="bg-white rounded-xl border border-blue-200 shadow-sm p-5 space-y-4"
        >
          <h4 className="text-sm font-semibold text-slate-900">Create Custom Payer Policy</h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input
              value={policyId}
              onChange={(e) => setPolicyId(e.target.value)}
              placeholder="Policy ID"
              className="px-3 py-2 text-sm border rounded-lg font-mono"
              required
            />
            <input
              value={payerId}
              onChange={(e) => setPayerId(e.target.value)}
              placeholder="Payer ID (e.g. UHC)"
              className="px-3 py-2 text-sm border rounded-lg"
              required
            />
            <input
              value={payerName}
              onChange={(e) => setPayerName(e.target.value)}
              placeholder="Payer Full Name"
              className="px-3 py-2 text-sm border rounded-lg"
              required
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Policy Title"
              className="sm:col-span-2 px-3 py-2 text-sm border rounded-lg"
              required
            />
            <input
              value={cptCodes}
              onChange={(e) => setCptCodes(e.target.value)}
              placeholder="CPT Codes (comma sep)"
              className="px-3 py-2 text-sm border rounded-lg font-mono"
              required
            />
            <input
              value={icdCodes}
              onChange={(e) => setIcdCodes(e.target.value)}
              placeholder="ICD-10 Codes (comma sep)"
              className="px-3 py-2 text-sm border rounded-lg font-mono"
              required
            />
          </div>
          <div className="flex items-center justify-between gap-3">
            <label className="text-xs text-slate-600 flex items-center gap-2">
              Minimum Age Rule:
              <input
                type="number"
                value={minAge}
                onChange={(e) => setMinAge(Number(e.target.value))}
                className="w-20 px-2 py-1 border rounded-md"
              />
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
              >
                Save Policy
              </button>
            </div>
          </div>
        </form>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map((policy) => (
          <div
            key={policy.policy_id}
            className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 flex flex-col justify-between gap-4"
          >
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="inline-block px-2 py-0.5 text-[11px] font-bold rounded bg-indigo-50 text-indigo-700 border border-indigo-200 mb-1">
                    {policy.payer_id} · {policy.payer_name}
                  </span>
                  <h4 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
                    <BookOpen className="w-4 h-4 text-blue-600 shrink-0" />
                    {policy.policy_title || policy.policy_id}
                  </h4>
                  <p className="text-xs font-mono text-slate-400">{policy.policy_id}</p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDelete(policy.policy_id)}
                  className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg"
                  title="Remove policy"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5 pt-1">
                {policy.procedure_codes.map((c) => (
                  <span
                    key={c}
                    className="px-2 py-0.5 text-[11px] font-mono font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200 rounded"
                  >
                    CPT {c}
                  </span>
                ))}
                {policy.diagnosis_codes.map((d) => (
                  <span
                    key={d}
                    className="px-2 py-0.5 text-[11px] font-mono bg-rose-50 text-rose-800 border border-rose-200 rounded"
                  >
                    {d}
                  </span>
                ))}
              </div>

              {policy.medical_necessity && (
                <p className="text-xs text-slate-600 leading-relaxed pt-1">
                  {policy.medical_necessity.description}
                </p>
              )}
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-500 pt-3 border-t border-slate-100">
              <span>{policy.rules.length} weighted rule(s)</span>
              <span>
                Approve ≥ {Math.round(policy.auto_approve_threshold * 100)}% · Deny ≤{' '}
                {Math.round(policy.auto_deny_threshold * 100)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
