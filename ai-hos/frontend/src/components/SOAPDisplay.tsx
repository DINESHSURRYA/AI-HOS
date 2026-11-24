/**
 * Interactive SOAP note viewer & editor with entity coding, HIPAA PHI shield,
 * FHIR R4 export modal, EHR approval, and one-click Prior Auth handoff.
 */
import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Edit2,
  Save,
  FileText,
  ShieldCheck,
  Download,
  Send,
  X,
  Copy,
  Check,
} from 'lucide-react';
import type { SOAPNote } from '../types/clinical';

interface SOAPDisplayProps {
  sessionId: string;
  note: SOAPNote;
  phiRedactions?: string[];
  onSave?: (updated: SOAPNote, approve?: boolean) => Promise<void> | void;
  onExportFhir?: () => Promise<Record<string, unknown>>;
  onSendToPriorAuth?: (note: SOAPNote) => void;
  readOnly?: boolean;
}

export function SOAPDisplay({
  sessionId,
  note,
  phiRedactions = [],
  onSave,
  onExportFhir,
  onSendToPriorAuth,
  readOnly = false,
}: SOAPDisplayProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedNote, setEditedNote] = useState<SOAPNote>(note);
  const [saving, setSaving] = useState(false);
  const [fhirBundle, setFhirBundle] = useState<Record<string, unknown> | null>(null);
  const [exportingFhir, setExportingFhir] = useState(false);
  const [copiedFhir, setCopiedFhir] = useState(false);

  useEffect(() => {
    setEditedNote(note);
    setIsEditing(false);
  }, [note, sessionId]);

  const handleSave = async (approve = false) => {
    setSaving(true);
    try {
      await onSave?.(editedNote, approve);
      setIsEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleExportFhir = async () => {
    if (!onExportFhir) return;
    setExportingFhir(true);
    try {
      const bundle = await onExportFhir();
      setFhirBundle(bundle);
    } finally {
      setExportingFhir(false);
    }
  };

  const downloadFhirJson = () => {
    if (!fhirBundle) return;
    const blob = new Blob([JSON.stringify(fhirBundle, null, 2)], {
      type: 'application/fhir+json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ai-hos-fhir-r4-${sessionId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyFhirJson = async () => {
    if (!fhirBundle) return;
    await navigator.clipboard.writeText(JSON.stringify(fhirBundle, null, 2));
    setCopiedFhir(true);
    setTimeout(() => setCopiedFhir(false), 2000);
  };

  const sections = [
    { key: 'subjective', label: 'Subjective (S)', color: 'bg-sky-50/70 border-sky-200' },
    { key: 'objective', label: 'Objective (O)', color: 'bg-emerald-50/70 border-emerald-200' },
    { key: 'assessment', label: 'Assessment (A)', color: 'bg-amber-50/70 border-amber-200' },
    { key: 'plan', label: 'Plan (P)', color: 'bg-indigo-50/70 border-indigo-200' },
  ] as const;

  const entityColor = (type: string) => {
    switch (type) {
      case 'diagnosis':
        return 'bg-rose-100 text-rose-800 border-rose-200';
      case 'medication':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      case 'procedure':
        return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'allergy':
        return 'bg-orange-100 text-orange-800 border-orange-200';
      case 'vital':
        return 'bg-purple-100 text-purple-800 border-purple-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-600" />
            <h3 className="text-lg font-semibold text-slate-900">Structured SOAP Note</h3>
            {note.approved && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                <CheckCircle2 className="w-3.5 h-3.5" /> Signed & Approved
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Engine: {note.model_used || 'ai-hos-clinical-engine-v2'} · Session {sessionId.slice(0, 8)}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(note.phi_redacted_count || 0) > 0 && (
            <span
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-teal-50 text-teal-800 border border-teal-200"
              title={`Redacted PHI categories: ${phiRedactions.join(', ') || 'HIPAA Safe Harbor'}`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              HIPAA Shield: {note.phi_redacted_count} PHI redacted
            </span>
          )}

          <span
            className={`px-3 py-1 rounded-full text-xs font-semibold ${
              note.confidence_score >= 0.8
                ? 'bg-emerald-100 text-emerald-800'
                : note.confidence_score >= 0.6
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-rose-100 text-rose-800'
            }`}
          >
            AI Confidence: {Math.round(note.confidence_score * 100)}%
          </span>

          {!readOnly && (
            <button
              type="button"
              disabled={saving}
              onClick={() => (isEditing ? handleSave(false) : setIsEditing(true))}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors"
            >
              {isEditing ? (
                <>
                  <Save className="w-3.5 h-3.5" /> {saving ? 'Saving...' : 'Save Changes'}
                </>
              ) : (
                <>
                  <Edit2 className="w-3.5 h-3.5" /> Edit Note
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Extracted Coded Clinical Entities */}
      {note.entities.length > 0 && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
            Extracted Clinical Entities & Standardized Codes ({note.entities.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {note.entities.map((entity, idx) => (
              <span
                key={`${entity.text}-${idx}`}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${entityColor(
                  entity.entity_type
                )}`}
                title={`Type: ${entity.entity_type} · Confidence: ${Math.round(
                  entity.confidence * 100
                )}%`}
              >
                <span className="uppercase text-[10px] opacity-70 font-bold">
                  {entity.entity_type.slice(0, 4)}
                </span>
                <span>{entity.text}</span>
                {entity.dosage && (
                  <span className="text-[11px] opacity-80">({entity.dosage})</span>
                )}
                {entity.icd10 && (
                  <span className="px-1 py-0.2 bg-white/70 rounded text-[10px] font-mono font-semibold">
                    ICD-10 {entity.icd10}
                  </span>
                )}
                {entity.cpt && (
                  <span className="px-1 py-0.2 bg-white/70 rounded text-[10px] font-mono font-semibold">
                    CPT {entity.cpt}
                  </span>
                )}
                {entity.rxnorm && (
                  <span className="px-1 py-0.2 bg-white/70 rounded text-[10px] font-mono font-semibold">
                    RxNorm {entity.rxnorm}
                  </span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* SOAP Sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sections.map(({ key, label, color }) => (
          <div key={key} className={`p-4 rounded-xl border ${color}`}>
            <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
              {label}
            </h4>
            {isEditing ? (
              <textarea
                value={editedNote[key]}
                onChange={(e) =>
                  setEditedNote({ ...editedNote, [key]: e.target.value })
                }
                className="w-full p-2.5 bg-white border border-slate-300 rounded-lg min-h-[120px] text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            ) : (
              <p className="text-slate-800 whitespace-pre-wrap text-sm leading-relaxed">
                {note[key]}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Action Footer */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-100">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={exportingFhir}
            onClick={handleExportFhir}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            {exportingFhir ? 'Exporting...' : 'Export FHIR R4 Bundle'}
          </button>

          {onSendToPriorAuth && (
            <button
              type="button"
              onClick={() => onSendToPriorAuth(editedNote)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-lg transition-colors"
            >
              <Send className="w-4 h-4" />
              Send to Prior Authorization
            </button>
          )}
        </div>

        {!readOnly && (
          <button
            type="button"
            disabled={saving}
            onClick={() => handleSave(true)}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors disabled:opacity-50"
          >
            <CheckCircle2 className="w-4 h-4" />
            {note.approved ? 'Update Approved Note' : 'Approve & Save to EHR'}
          </button>
        )}
      </div>

      {/* FHIR R4 Bundle Modal */}
      {fhirBundle && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-3xl max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200">
              <div>
                <h4 className="font-semibold text-slate-900">HL7 FHIR R4 Document Bundle</h4>
                <p className="text-xs text-slate-500">
                  Contains Composition (LOINC 11506-3), Condition (ICD-10), MedicationRequest (RxNorm), and ServiceRequest (CPT)
                </p>
              </div>
              <button
                type="button"
                onClick={() => setFhirBundle(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <pre className="flex-1 overflow-auto p-4 text-xs font-mono bg-slate-950 text-emerald-300">
              {JSON.stringify(fhirBundle, null, 2)}
            </pre>
            <div className="flex justify-end gap-2 px-5 py-3 border-t border-slate-200 bg-slate-50 rounded-b-2xl">
              <button
                type="button"
                onClick={copyFhirJson}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 hover:bg-slate-100 rounded-lg"
              >
                {copiedFhir ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedFhir ? 'Copied!' : 'Copy JSON'}
              </button>
              <button
                type="button"
                onClick={downloadFhirJson}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
              >
                <Download className="w-3.5 h-3.5" /> Download .json
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
