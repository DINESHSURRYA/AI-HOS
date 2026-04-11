/**
 * Display generated SOAP note with editing capabilities
 */
import { useState } from 'react';
import { Check, Edit2, Save, FileText } from 'lucide-react';

interface SOAPNote {
  subjective: string;
  objective: string;
  assessment: string;
  plan: string;
  entities: Array<{
    text: string;
    entity_type: string;
    icd10?: string;
    rxnorm?: string;
    confidence: number;
  }>;
  confidence_score: number;
}

interface SOAPDisplayProps {
  note: SOAPNote;
  onSave?: (note: SOAPNote) => void;
  readOnly?: boolean;
}

export function SOAPDisplay({ note, onSave, readOnly = false }: SOAPDisplayProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedNote, setEditedNote] = useState(note);

  const handleSave = () => {
    onSave?.(editedNote);
    setIsEditing(false);
  };

  const sections = [
    { key: 'subjective', label: 'Subjective', color: 'bg-blue-50 border-blue-200' },
    { key: 'objective', label: 'Objective', color: 'bg-green-50 border-green-200' },
    { key: 'assessment', label: 'Assessment', color: 'bg-yellow-50 border-yellow-200' },
    { key: 'plan', label: 'Plan', color: 'bg-purple-50 border-purple-200' },
  ] as const;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-gray-600" />
          <h3 className="text-lg font-semibold">Generated SOAP Note</h3>
        </div>
        
        <div className="flex items-center gap-3">
          {/* Confidence badge */}
          <span className={`
            px-3 py-1 rounded-full text-sm font-medium
            ${note.confidence_score >= 0.8 ? 'bg-green-100 text-green-800' : 
              note.confidence_score >= 0.6 ? 'bg-yellow-100 text-yellow-800' : 
              'bg-red-100 text-red-800'}
          `}>
            AI Confidence: {Math.round(note.confidence_score * 100)}%
          </span>

          {!readOnly && (
            <button
              onClick={() => isEditing ? handleSave() : setIsEditing(true)}
              className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
            >
              {isEditing ? (
                <><Save className="w-4 h-4" /> Save</>
              ) : (
                <><Edit2 className="w-4 h-4" /> Edit</>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Extracted Entities */}
      {note.entities.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {note.entities.map((entity, idx) => (
            <span
              key={idx}
              className={`
                inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium
                ${entity.entity_type === 'diagnosis' ? 'bg-red-100 text-red-800' :
                  entity.entity_type === 'medication' ? 'bg-blue-100 text-blue-800' :
                  entity.entity_type === 'procedure' ? 'bg-green-100 text-green-800' :
                  'bg-gray-100 text-gray-800'}
              `}
              title={`Confidence: ${Math.round(entity.confidence * 100)}%`}
            >
              {entity.text}
              {entity.icd10 && <span className="text-[10px] opacity-75">({entity.icd10})</span>}
              {entity.rxnorm && <span className="text-[10px] opacity-75">(Rx{entity.rxnorm})</span>}
            </span>
          ))}
        </div>
      )}

      {/* SOAP Sections */}
      <div className="grid gap-4">
        {sections.map(({ key, label, color }) => (
          <div
            key={key}
            className={`p-4 rounded-lg border ${color}`}
          >
            <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">
              {label}
            </h4>
            {isEditing ? (
              <textarea
                value={editedNote[key]}
                onChange={(e) => setEditedNote({ ...editedNote, [key]: e.target.value })}
                className="w-full p-2 border rounded-md min-h-[80px] text-sm"
              />
            ) : (
              <p className="text-gray-800 whitespace-pre-wrap text-sm leading-relaxed">
                {note[key]}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-4 border-t">
        <button className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-md">
          Export to FHIR
        </button>
        <button className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md">
          Approve & Save to EHR
        </button>
      </div>
    </div>
  );
}
5. Database Schemas
