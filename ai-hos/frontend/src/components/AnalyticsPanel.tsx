/**
 * Hospital Operations Analytics & Recent Encounters Panel.
 */
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { Activity, FileCheck, ShieldCheck, CheckCircle2, RefreshCw } from 'lucide-react';
import type { ClinicalDocStats, PriorAuthStats, VoiceSession } from '../types/clinical';

interface AnalyticsPanelProps {
  docStats: ClinicalDocStats | null;
  authStats: PriorAuthStats | null;
  sessions: VoiceSession[];
  onOpenSession: (session: VoiceSession) => void;
  onRefresh: () => void;
}

const PIE_COLORS = ['#10b981', '#f59e0b', '#f43f5e'];

export function AnalyticsPanel({
  docStats,
  authStats,
  sessions,
  onOpenSession,
  onRefresh,
}: AnalyticsPanelProps) {
  const entityChartData = docStats
    ? Object.entries(docStats.entity_breakdown).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        count: value,
      }))
    : [];

  const decisionPieData = authStats
    ? [
        { name: 'Auto Approved', value: authStats.auto_approved },
        { name: 'Escalated', value: authStats.escalated },
        { name: 'Auto Denied', value: authStats.auto_denied },
      ].filter((d) => d.value > 0)
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-900">
            Hospital AI Operations Overview
          </h3>
          <p className="text-xs text-slate-500">
            Live telemetry aggregated from Clinical Doc AI (:8000) and Prior Auth Engine (:8001)
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Metrics
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-medium">
            Clinical Sessions <Activity className="w-4 h-4 text-blue-600" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {docStats?.total_sessions ?? 0}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {docStats?.completed_sessions ?? 0} SOAP notes generated
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-medium">
            EHR Approved Notes <FileCheck className="w-4 h-4 text-emerald-600" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {docStats?.approved_notes ?? 0}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Avg AI Confidence: {Math.round((docStats?.avg_confidence ?? 0) * 100)}%
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-medium">
            Prior Auth Evaluations <ShieldCheck className="w-4 h-4 text-indigo-600" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {authStats?.total_evaluations ?? 0}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {authStats?.total_policies ?? 0} active payer policies
          </p>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-medium">
            Auto-Approval Rate <CheckCircle2 className="w-4 h-4 text-teal-600" />
          </div>
          <p className="text-2xl font-bold text-slate-900 mt-2">
            {authStats?.auto_approval_rate ?? 0}%
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {docStats?.total_entities_extracted ?? 0} total clinical codes extracted
          </p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h4 className="text-sm font-semibold text-slate-900 mb-4">
            Extracted Medical Entities by Category
          </h4>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={entityChartData}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h4 className="text-sm font-semibold text-slate-900 mb-4">
            Prior Authorization Decision Distribution
          </h4>
          <div className="h-60 flex items-center justify-center">
            {decisionPieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={decisionPieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={85}
                    paddingAngle={4}
                    label
                  >
                    {decisionPieData.map((_, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={PIE_COLORS[index % PIE_COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-slate-400">
                Run a Prior Authorization evaluation to populate decision analytics.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Recent Encounters Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-100">
          <h4 className="text-sm font-semibold text-slate-900">
            Recent Clinical Encounters ({sessions.length})
          </h4>
        </div>
        {sessions.length === 0 ? (
          <p className="p-6 text-xs text-slate-500 text-center">
            No encounters recorded yet. Generate your first SOAP note in the Clinical Documentation tab.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 uppercase">
                <tr>
                  <th className="px-4 py-2.5">Patient</th>
                  <th className="px-4 py-2.5">Provider</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Entities</th>
                  <th className="px-4 py-2.5">Confidence</th>
                  <th className="px-4 py-2.5">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sessions.map((sess) => (
                  <tr
                    key={sess.session_id}
                    onClick={() => onOpenSession(sess)}
                    className="hover:bg-blue-50/50 cursor-pointer"
                  >
                    <td className="px-4 py-2.5 font-mono font-medium text-slate-800">
                      {sess.patient_id}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-slate-600">
                      {sess.provider_id}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded-full font-semibold ${
                          sess.status === 'approved'
                            ? 'bg-emerald-100 text-emerald-800'
                            : sess.status === 'completed'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {sess.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      {sess.soap_note?.entities.length ?? 0}
                    </td>
                    <td className="px-4 py-2.5">
                      {sess.soap_note
                        ? `${Math.round(sess.soap_note.confidence_score * 100)}%`
                        : '-'}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500">
                      {new Date(sess.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
