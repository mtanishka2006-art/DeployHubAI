"use client";

import * as React from "react";
import {
  Activity,
  AlertOctagon,
  RefreshCw,
  ShieldCheck,
  Rocket,
  Github,
  Cloud,
  ClipboardList,
  BellRing,
  Boxes,
  Plug,
} from "lucide-react";

const CONNECTOR_ICONS: Record<string, typeof Activity> = {
  github_actions: Github,
  aws: Cloud,
  jira: ClipboardList,
  pagerduty: BellRing,
  datadog: Activity,
  kubernetes: Boxes,
};
import { getOverview } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Gauge } from "@/components/gauge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Badge,
  severityVariant,
  statusVariant,
} from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Loading, ErrorState, EmptyState } from "@/components/states";
import { formatDate, timeAgo } from "@/lib/utils";

function Stat({
  label,
  value,
  sub,
  icon,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
  icon: React.ReactNode;
  accent?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-4 p-5">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          <p className={`mt-1 text-3xl font-bold tabular-nums ${accent || ""}`}>
            {value}
          </p>
          {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
        </div>
        <div className="rounded-lg border border-border bg-background/40 p-3 text-primary">
          {icon}
        </div>
      </CardContent>
    </Card>
  );
}

export default function OverviewPage() {
  const [data, setData] = React.useState<Overview | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getOverview());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load overview");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Overview Dashboard"
        description="Real-time posture across services, incidents, and disaster recovery."
        icon={<Activity className="h-5 w-5" />}
      />

      {error && <ErrorState message={error} className="mb-6" />}
      {loading && !data ? (
        <Loading label="Loading mission control telemetry…" />
      ) : data ? (
        <div className="space-y-6">
          {/* Top row: gauge + stats */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
            <Card className="lg:col-span-1">
              <CardHeader>
                <CardTitle>System Health</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col items-center">
                <Gauge value={data.system_health.score} label="score" />
                <Badge
                  variant={statusVariant(data.system_health.status)}
                  className="mt-3 capitalize"
                >
                  {data.system_health.status}
                </Badge>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:col-span-3 lg:grid-cols-3">
              <Stat
                label="Active Incidents"
                value={data.active_incidents}
                sub="Open across all services"
                icon={<AlertOctagon className="h-5 w-5" />}
                accent={
                  data.active_incidents > 0 ? "text-amber-400" : "text-emerald-400"
                }
              />
              <Stat
                label="Recovery Success"
                value={`${Math.round(data.recovery_success_rate)}%`}
                sub="Automated recovery rate"
                icon={<RefreshCw className="h-5 w-5" />}
                accent="text-emerald-400"
              />
              <Stat
                label="DR Readiness"
                value={Math.round(data.dr_readiness.score)}
                sub={data.dr_readiness.readiness}
                icon={<ShieldCheck className="h-5 w-5" />}
                accent="text-sky-400"
              />

              {/* Health by service */}
              <Card className="sm:col-span-2 lg:col-span-3">
                <CardHeader>
                  <CardTitle>Health by Service</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {data.health_by_service.length === 0 ? (
                    <EmptyState title="No service health data" />
                  ) : (
                    data.health_by_service.map((s) => (
                      <div key={s.service}>
                        <div className="mb-1 flex items-center justify-between text-xs">
                          <span className="flex items-center gap-1.5 font-medium">
                            {s.service}
                            {s.connectors && s.connectors.length > 0 && (
                              <span
                                className="flex items-center gap-1"
                                title={`Live data from: ${s.connectors.join(", ")}`}
                              >
                                {s.connectors.map((c) => {
                                  const Ico = CONNECTOR_ICONS[c] || Plug;
                                  return (
                                    <Ico
                                      key={c}
                                      className="h-3 w-3 text-emerald-400"
                                    />
                                  );
                                })}
                              </span>
                            )}
                          </span>
                          <div className="flex items-center gap-2">
                            <Badge
                              variant={statusVariant(s.status)}
                              className="capitalize"
                            >
                              {s.status}
                            </Badge>
                            <span className="tabular-nums text-muted-foreground">
                              {Math.round(s.score)}
                            </span>
                          </div>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${Math.max(0, Math.min(100, s.score))}%`,
                              background:
                                s.score >= 80
                                  ? "hsl(152 70% 45%)"
                                  : s.score >= 60
                                  ? "hsl(40 90% 55%)"
                                  : "hsl(0 80% 60%)",
                            }}
                          />
                        </div>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Deployments + Timeline */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Rocket className="h-4 w-4" /> Recent Deployments
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {data.recent_deployments.length === 0 ? (
                  <EmptyState title="No recent deployments" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Service</TableHead>
                        <TableHead>Env</TableHead>
                        <TableHead>Version</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>When</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.recent_deployments.map((d) => (
                        <TableRow key={d.id}>
                          <TableCell className="font-medium">
                            {d.service}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {d.environment}
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {d.version}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={statusVariant(d.status)}
                              className="capitalize"
                            >
                              {d.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {timeAgo(d.timestamp)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertOctagon className="h-4 w-4" /> Incident Timeline
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.incident_timeline.length === 0 ? (
                  <EmptyState title="No incidents on the timeline" />
                ) : (
                  <ol className="relative space-y-4 border-l border-border pl-5">
                    {data.incident_timeline.map((i) => (
                      <li key={i.id} className="relative">
                        <span className="absolute -left-[26px] top-1 flex h-3 w-3 items-center justify-center rounded-full border-2 border-background bg-primary" />
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={severityVariant(i.severity)}>
                            {i.severity}
                          </Badge>
                          <span className="text-sm font-medium">{i.title}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{i.service}</span>
                          <span>•</span>
                          <Badge
                            variant={statusVariant(i.status)}
                            className="capitalize"
                          >
                            {i.status}
                          </Badge>
                          <span>•</span>
                          <span>{formatDate(i.timestamp)}</span>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}
