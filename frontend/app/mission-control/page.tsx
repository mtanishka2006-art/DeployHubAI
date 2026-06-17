"use client";

import * as React from "react";
import {
  Radar,
  Loader2,
  Activity,
  ShieldCheck,
  Search,
  Wrench,
  History,
  FileText,
  Play,
} from "lucide-react";
import { runMissionControl, getMissionControlReports } from "@/lib/api";
import type { MissionControlReport, RecommendedAction } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, severityVariant, statusVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { Loading, ErrorState, EmptyState } from "@/components/states";
import { Gauge } from "@/components/gauge";
import { formatDate } from "@/lib/utils";

function asText(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "object" && v && "status" in (v as any))
    return String((v as any).status);
  if (typeof v === "object" && v && "readiness" in (v as any))
    return String((v as any).readiness);
  return String(v);
}

const SERVICES = [
  "checkout-service",
  "payments-service",
  "order-service",
  "inventory-service",
  "user-service",
  "api-gateway",
  "search-service",
];

export default function MissionControlPage() {
  const [description, setDescription] = React.useState(
    "Elevated 5xx errors and latency on checkout after the latest release"
  );
  const [service, setService] = React.useState("checkout-service");
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [report, setReport] = React.useState<MissionControlReport | null>(null);
  const [reports, setReports] = React.useState<MissionControlReport[]>([]);

  const loadReports = React.useCallback(async () => {
    try {
      setReports(await getMissionControlReports({ limit: 5 }));
    } catch {
      /* non-fatal */
    }
  }, []);

  React.useEffect(() => {
    loadReports();
  }, [loadReports]);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const r = await runMissionControl({
        description,
        service,
        environment: "prod",
      });
      setReport(r);
      loadReports();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mission Control run failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Mission Control"
        description="Orchestrates the Monitoring → RCA → DR → Memory → Recovery agent pipeline into a single unified incident report."
        icon={<Radar className="h-5 w-5" />}
      />

      <div className="grid gap-6 lg:grid-cols-[380px_minmax(0,1fr)]">
        {/* Launch panel */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Play className="h-4 w-4" /> Launch Analysis
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={run} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Incident description
                  </label>
                  <Textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Service
                  </label>
                  <Select
                    value={service}
                    onChange={(e) => setService(e.target.value)}
                  >
                    {SERVICES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </Select>
                </div>
                <p className="rounded-md border border-border bg-background/40 px-3 py-2 text-[11px] text-muted-foreground">
                  Severity is determined automatically by the agents from system
                  health, root cause, and DR readiness — it appears in the report.
                </p>
                {error && <ErrorState message={error} />}
                <Button type="submit" disabled={running} className="w-full">
                  {running ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Running agent pipeline…
                    </>
                  ) : (
                    <>
                      <Radar className="h-4 w-4" />
                      Run Mission Control
                    </>
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <FileText className="h-4 w-4" /> Recent Reports
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {reports.length === 0 ? (
                <p className="text-xs text-muted-foreground">No reports yet.</p>
              ) : (
                reports.map((r, idx) => (
                  <button
                    key={idx}
                    onClick={() => setReport(r)}
                    className="w-full rounded-md border border-border p-2 text-left text-xs transition-colors hover:border-primary"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        #{r.incident_id ?? "—"}
                      </span>
                      <Badge variant={statusVariant(asText(r.system_health))}>
                        {asText(r.system_health)}
                      </Badge>
                    </div>
                    <p className="mt-1 truncate text-muted-foreground">
                      {r.root_cause}
                    </p>
                  </button>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        {/* Report */}
        <div>
          {running ? (
            <Card>
              <CardContent>
                <Loading label="Agents analyzing: monitoring → RCA → DR → memory → recovery…" />
              </CardContent>
            </Card>
          ) : !report ? (
            <Card className="flex h-full items-center justify-center">
              <CardContent className="py-16">
                <EmptyState
                  title="No report yet"
                  description="Launch an analysis to generate a unified incident report from all agents."
                  icon={<Radar className="h-8 w-8" />}
                />
              </CardContent>
            </Card>
          ) : (
            <UnifiedReport report={report} />
          )}
        </div>
      </div>
    </div>
  );
}

function UnifiedReport({ report }: { report: MissionControlReport }) {
  const mon = report.monitoring as
    | { health_status?: string; health_score?: number; confidence?: number }
    | undefined;
  const monScore = mon?.health_score;
  const dr = report.dr as
    | { dr_score?: number; readiness?: string; confidence?: number }
    | undefined;
  const drScore = dr?.dr_score ?? 0;
  const actions: RecommendedAction[] = (report.recommended_actions ||
    []) as RecommendedAction[];

  return (
    <div className="space-y-6">
      {/* Executive summary */}
      <Card className="border-primary/30 bg-primary/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" /> Executive Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed">{report.executive_summary}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {report.severity && (
              <Badge variant={severityVariant(report.severity)}>
                Severity: {report.severity}
              </Badge>
            )}
            <Badge variant={statusVariant(asText(report.system_health))}>
              Health: {asText(report.system_health)}
            </Badge>
            <Badge variant={statusVariant(asText(report.dr_readiness))}>
              DR: {asText(report.dr_readiness)}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Agent scorecards */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Activity className="h-4 w-4" /> Monitoring Agent
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-4">
            {typeof monScore === "number" && (
              <Gauge value={monScore} size={96} label="health" />
            )}
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>
                Status:{" "}
                <span className="text-foreground">{mon?.health_status}</span>
              </p>
              <p>
                Confidence: {((mon?.confidence ?? 0) * 100).toFixed(0)}%
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <ShieldCheck className="h-4 w-4" /> DR Agent
            </CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-4">
            <Gauge value={drScore} size={96} label="DR score" />
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>
                Readiness:{" "}
                <span className="text-foreground">{dr?.readiness}</span>
              </p>
              <p>
                Confidence: {((dr?.confidence ?? 0) * 100).toFixed(0)}%
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* RCA */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Search className="h-4 w-4" /> Root Cause Analysis
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{report.root_cause}</p>
          {report.rca?.confidence != null && (
            <Badge variant="info" className="mt-2">
              {(report.rca.confidence * 100).toFixed(0)}% confidence
            </Badge>
          )}
        </CardContent>
      </Card>

      {/* Recommended actions */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-4 w-4" /> Recovery Recommendations
          </CardTitle>
        </CardHeader>
        <CardContent>
          {actions.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No actions recommended.
            </p>
          ) : (
            <ol className="space-y-3">
              {actions.map((a, idx) => (
                <li
                  key={idx}
                  className="rounded-md border border-border bg-background/40 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex gap-3">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
                        {a.priority ?? idx + 1}
                      </span>
                      <span className="text-sm font-medium">{a.action}</span>
                    </div>
                    {a.risk && (
                      <Badge variant={severityVariant(a.risk)}>
                        {a.risk} risk
                      </Badge>
                    )}
                  </div>
                  {a.rationale && (
                    <p className="mt-2 pl-8 text-xs text-muted-foreground">
                      {a.rationale}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>

      {/* Similar incidents */}
      {report.similar_incidents && report.similar_incidents.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <History className="h-4 w-4" /> Similar Historical Incidents
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {report.similar_incidents.map((s, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between gap-3 rounded-md border border-border bg-background/40 p-3"
              >
                <div>
                  <p className="text-sm font-medium">{s.title}</p>
                  {s.root_cause && (
                    <p className="text-xs text-muted-foreground">
                      {s.root_cause}
                    </p>
                  )}
                </div>
                {typeof s.score === "number" && (
                  <Badge variant="info">
                    {(s.score <= 1 ? s.score * 100 : s.score).toFixed(0)}%
                  </Badge>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
