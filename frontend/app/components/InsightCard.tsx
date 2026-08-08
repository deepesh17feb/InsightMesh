"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  Sparkles,
  Table2,
  Terminal,
  Lightbulb,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
} from "lucide-react";

export interface Insight {
  question: string;
  executiveSummary: string;
  confidence: {
    score: number;
    rationale: string;
    sample_size_component?: number;
    effect_size_component?: number;
    known_issue_component?: number;
    cut_consistency_component?: number;
  };
  knownIssueMatch: boolean;
  matchedKnownIssue: string;
  cuts: Record<string, Array<Record<string, any>>>;
  views: {
    metric_deltas: Array<{ metric: string; baseline: string; observed: string; delta: string; impact: string }>;
  };
  sqlQueries: string[];
  specId: string;
  traceId: string;
  traceUrl: string;
}

function confidenceTier(score: number): { color: "emerald" | "amber" | "rose"; label: string } {
  if (score >= 0.8) return { color: "emerald", label: "High confidence" };
  if (score >= 0.5) return { color: "amber", label: "Moderate confidence" };
  return { color: "rose", label: "Low confidence" };
}

const TIER_CLASSES = {
  emerald: {
    bar: "bg-emerald-500",
    badgeBg: "bg-emerald-500/10",
    badgeText: "text-emerald-400",
    badgeBorder: "border-emerald-500/30",
  },
  amber: {
    bar: "bg-amber-500",
    badgeBg: "bg-amber-500/10",
    badgeText: "text-amber-400",
    badgeBorder: "border-amber-500/30",
  },
  rose: {
    bar: "bg-rose-500",
    badgeBg: "bg-rose-500/10",
    badgeText: "text-rose-400",
    badgeBorder: "border-rose-500/30",
  },
} as const;

function SectionEyebrow({ icon: Icon, children }: { icon: React.ElementType; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500 font-semibold mb-2">
      <Icon className="w-3.5 h-3.5" />
      <span>{children}</span>
    </div>
  );
}

export default function InsightCard({ insight }: { insight: Insight }) {
  const tier = confidenceTier(insight.confidence?.score ?? 0);
  const tierClasses = TIER_CLASSES[tier.color];
  const [sqlOpen, setSqlOpen] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const handleCopySql = (idx: number, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const cutEntries = Object.entries(insight.cuts || {}).filter(([, rows]) => rows && rows.length > 0);
  const metricDeltas = insight.views?.metric_deltas || [];
  const hasFacts = cutEntries.length > 0 || metricDeltas.length > 0;
  const sqlQueries = insight.sqlQueries || [];

  return (
    <div className="relative rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden">
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${tierClasses.bar}`} />
      <div className="pl-5 pr-4 py-4 space-y-4">
        <div>
          <div className="flex items-start justify-between gap-3">
            <SectionEyebrow icon={Sparkles}>Overall Summary</SectionEyebrow>
            <span
              className={`shrink-0 px-2 py-0.5 rounded-md border text-[10px] font-semibold ${tierClasses.badgeBg} ${tierClasses.badgeText} ${tierClasses.badgeBorder}`}
              title={tier.label}
            >
              {"●"} {(insight.confidence?.score ?? 0).toFixed(2)}
            </span>
          </div>
          <div className="prose prose-invert prose-sm max-w-none text-sm leading-relaxed text-slate-200 prose-p:my-0 prose-p:leading-relaxed">
            <ReactMarkdown>{insight.executiveSummary}</ReactMarkdown>
          </div>
        </div>

        {hasFacts && (
          <div className="border-t border-slate-800 pt-4">
            <SectionEyebrow icon={Table2}>Facts</SectionEyebrow>
            {metricDeltas.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                {metricDeltas.map((m, idx) => (
                  <div key={idx} className="rounded-lg bg-slate-950/60 border border-slate-800 px-2.5 py-2">
                    <div className="text-[10px] text-slate-500 truncate">{m.metric}</div>
                    <div className="text-sm font-semibold text-slate-100">{m.observed}</div>
                    <div className="text-[10px] text-slate-400">{m.delta}</div>
                  </div>
                ))}
              </div>
            )}
            {cutEntries.map(([dim, rows]) => {
              const columns = Object.keys(rows[0] || {});
              return (
                <div key={dim} className="mb-3 last:mb-0 overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-slate-950/60 text-slate-400">
                        <th className="text-left px-2.5 py-1.5 font-medium">{dim}</th>
                        {columns
                          .filter((c) => c !== dim)
                          .map((c) => (
                            <th key={c} className="text-right px-2.5 py-1.5 font-medium">
                              {c}
                            </th>
                          ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 8).map((row, ridx) => (
                        <tr key={ridx} className="border-t border-slate-800/80 text-slate-300">
                          <td className="px-2.5 py-1.5">{String(row[dim] ?? "")}</td>
                          {columns
                            .filter((c) => c !== dim)
                            .map((c) => (
                              <td key={c} className="text-right px-2.5 py-1.5 tabular-nums">
                                {String(row[c] ?? "")}
                              </td>
                            ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        )}

        {sqlQueries.length > 0 && (
          <div className="border-t border-slate-800 pt-4">
            <button
              onClick={() => setSqlOpen((v) => !v)}
              className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-slate-500 font-semibold mb-2 hover:text-slate-300 transition-colors"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>
                SQL ({sqlQueries.length} {sqlQueries.length === 1 ? "query" : "queries"})
              </span>
              {sqlOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            </button>
            {sqlOpen && (
              <div className="space-y-2">
                {sqlQueries.map((sql, idx) => (
                  <div key={idx} className="group relative rounded-lg bg-slate-950 border border-slate-800 px-3 py-2.5">
                    <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap break-all pr-8">{sql}</pre>
                    <button
                      onClick={() => handleCopySql(idx, sql)}
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-slate-200"
                    >
                      {copiedIdx === idx ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="border-t border-slate-800 pt-4">
          <SectionEyebrow icon={Lightbulb}>Why this is right</SectionEyebrow>
          <p className="text-xs leading-relaxed text-slate-300">{insight.confidence?.rationale}</p>
          {insight.knownIssueMatch && insight.matchedKnownIssue && (
            <div className="mt-2 px-2.5 py-1.5 rounded-md bg-blue-500/10 border border-blue-500/30 text-[11px] text-blue-300">
              {"🔗"} {insight.matchedKnownIssue}
            </div>
          )}
        </div>

        {insight.traceUrl && (
          <div className="border-t border-slate-800 pt-4 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
              <ExternalLink className="w-3.5 h-3.5" />
              <span className="uppercase tracking-wide font-semibold">Trace</span>
              <span className="font-mono text-slate-600">{"·"} {insight.traceId?.slice(0, 12)}</span>
            </div>
            <a
              href={insight.traceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] font-medium text-blue-400 hover:text-blue-300 flex items-center gap-1"
            >
              View <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
