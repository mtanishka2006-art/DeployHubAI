"use client";

import * as React from "react";
import {
  AlertOctagon,
  Plus,
  RefreshCw,
  X,
  Loader2,
  Sparkles,
  History,
} from "lucide-react";
import {
  createIncident,
  getIncident,
  getIncidents,
} from "@/lib/api";
import type { Incident, IncidentDetail } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
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
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Loading, ErrorState, EmptyState } from "@/components/states";
import { formatDate } from "@/lib/utils";

const SEVERITIES = ["critical", "high", "medium", "low"];
const STATUS_FILTERS = ["all", "open", "investigating", "resolved"];

export default function IncidentsPage() {
  const [incidents, setIncidents] = React.useState<Incident[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [statusFilter, setStatusFilter] = React.useState("all");
  const [selectedId, setSelectedId] = React.useState<number | string | null>(
    null
  );
  const [showCreate, setShowCreate] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params =
        statusFilter === "all" ? { limit: 100 } : { status: statusFilter, limit: 100 };
      setIncidents(await getIncidents(params));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  React.useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Incident Center"
        description="Triage, investigate, and resolve active and historical incidents."
        icon={<AlertOctagon className="h-5 w-5" />}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" />
              New Incident
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors ${
              statusFilter === s
                ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {error && <ErrorState message={error} className="mb-6" />}

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <Loading label="Loading incidents…" />
          ) : incidents.length === 0 ? (
            <EmptyState
              title="No incidents found"
              description="No incidents match the current filter."
              icon={<AlertOctagon className="h-8 w-8" />}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Service</TableHead>
                  <TableHead>Env</TableHead>
                  <TableHead>Detected</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {incidents.map((i) => (
                  <TableRow
                    key={i.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedId(i.id)}
                  >
                    <TableCell className="max-w-xs font-medium">
                      {i.title}
                    </TableCell>
                    <TableCell>
                      <Badge variant={severityVariant(i.severity)}>
                        {i.severity}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={statusVariant(i.status)}
                        className="capitalize"
                      >
                        {i.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {i.service}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {i.environment}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(i.detected_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedId !== null && (
        <IncidentDrawer
          id={selectedId}
          onClose={() => setSelectedId(null)}
        />
      )}

      {showCreate && (
        <CreateIncidentModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function IncidentDrawer({
  id,
  onClose,
}: {
  id: number | string;
  onClose: () => void;
}) {
  const [detail, setDetail] = React.useState<IncidentDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getIncident(id)
      .then((d) => active && setDetail(d))
      .catch(
        (err) =>
          active &&
          setError(err instanceof Error ? err.message : "Failed to load incident")
      )
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [id]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative h-full w-full max-w-xl overflow-y-auto border-l border-border bg-card shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border bg-card/95 px-6 py-4 backdrop-blur">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Incident Detail
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-6 p-6">
          {loading ? (
            <Loading label="Loading incident detail…" />
          ) : error ? (
            <ErrorState message={error} />
          ) : detail ? (
            <>
              <div>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge variant={severityVariant(detail.severity)}>
                    {detail.severity}
                  </Badge>
                  <Badge
                    variant={statusVariant(detail.status)}
                    className="capitalize"
                  >
                    {detail.status}
                  </Badge>
                </div>
                <h3 className="text-xl font-semibold">{detail.title}</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  {detail.service} · {detail.environment} ·{" "}
                  {formatDate(detail.detected_at)}
                </p>
                {(detail.summary || detail.description) && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    {detail.summary || detail.description}
                  </p>
                )}
              </div>

              {detail.root_cause && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Sparkles className="h-4 w-4" /> Root Cause Analysis
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed">{detail.root_cause}</p>
                  </CardContent>
                </Card>
              )}

              {detail.recommended_actions &&
                detail.recommended_actions.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Recommended Actions</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ol className="space-y-3">
                        {detail.recommended_actions.map((a, idx) => (
                          <li
                            key={idx}
                            className="rounded-md border border-border bg-background/40 p-3"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex gap-3">
                                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
                                  {a.priority ?? idx + 1}
                                </span>
                                <span className="text-sm font-medium">
                                  {a.action}
                                </span>
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
                    </CardContent>
                  </Card>
                )}

              {detail.similar_incidents &&
                detail.similar_incidents.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <History className="h-4 w-4" /> Similar Historical
                        Incidents
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {detail.similar_incidents.map((s, idx) => (
                        <div
                          key={s.id ?? idx}
                          className="rounded-md border border-border bg-background/40 p-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium">
                              {s.title}
                            </span>
                            {typeof s.score === "number" && (
                              <Badge variant="info">
                                {(s.score * (s.score <= 1 ? 100 : 1)).toFixed(0)}%
                                match
                              </Badge>
                            )}
                          </div>
                          {s.root_cause && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              {s.root_cause}
                            </p>
                          )}
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CreateIncidentModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [service, setService] = React.useState("");
  const [environment, setEnvironment] = React.useState("production");
  const [severity, setSeverity] = React.useState("high");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createIncident({ title, description, service, environment, severity });
      onCreated();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create incident"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Declare New Incident</CardTitle>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Title
              </label>
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="API latency spike in checkout"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Description
              </label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Observed symptoms, affected users, timeline…"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Service
                </label>
                <Input
                  value={service}
                  onChange={(e) => setService(e.target.value)}
                  placeholder="checkout-api"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Environment
                </label>
                <Select
                  value={environment}
                  onChange={(e) => setEnvironment(e.target.value)}
                >
                  <option value="production">production</option>
                  <option value="staging">staging</option>
                  <option value="development">development</option>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Severity
              </label>
              <Select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>

            {error && <ErrorState message={error} />}

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                Declare Incident
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
