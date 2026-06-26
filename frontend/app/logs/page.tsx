"use client";

import * as React from "react";
import { ScrollText, RefreshCw, Search } from "lucide-react";
import { getLogs, getLogServices, getLogSources } from "@/lib/api";
import type { LogEntry } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge, severityVariant } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Loading, ErrorState, EmptyState } from "@/components/states";
import { formatDate } from "@/lib/utils";

const SEVERITIES = ["all", "critical", "high", "medium", "low", "info"];

export default function LogsPage() {
  const [logs, setLogs] = React.useState<LogEntry[]>([]);
  const [services, setServices] = React.useState<string[]>([]);
  const [sources, setSources] = React.useState<string[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [severity, setSeverity] = React.useState("all");
  const [service, setService] = React.useState("all");
  const [source, setSource] = React.useState("all");
  const [search, setSearch] = React.useState("");

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: {
        source?: string;
        service?: string;
        severity?: string;
        q?: string;
        limit: number;
      } = { limit: 500 };
      if (source !== "all") params.source = source;
      if (severity !== "all") params.severity = severity;
      if (service !== "all") params.service = service;
      if (search.trim()) params.q = search.trim();
      setLogs(await getLogs(params));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
    } finally {
      setLoading(false);
    }
  }, [source, severity, service, search]);

  React.useEffect(() => {
    load();
  }, [load]);

  // Load the source list once.
  React.useEffect(() => {
    getLogSources()
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  // Services are scoped to the selected source; refetch + reset when it changes.
  React.useEffect(() => {
    setService("all");
    getLogServices(source === "all" ? undefined : source)
      .then(setServices)
      .catch(() => setServices([]));
  }, [source]);

  return (
    <div>
      <PageHeader
        title="Logs"
        description="Every log line ingested from your connected sources, in one searchable stream."
        icon={<ScrollText className="h-5 w-5" />}
        actions={
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        }
      />

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search log messages…"
            className="pl-9"
          />
        </div>
        <div className="w-44">
          <Select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="all">All sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <div className="w-40">
          <Select value={service} onChange={(e) => setService(e.target.value)}>
            <option value="all">All services</option>
            {services.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {SEVERITIES.map((s) => (
            <button
              key={s}
              onClick={() => setSeverity(s)}
              className={`rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors ${
                severity === s
                  ? "border-primary bg-primary/15 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorState message={error} className="mb-6" />}

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <Loading label="Loading logs…" />
          ) : logs.length === 0 ? (
            <EmptyState
              title="No logs found"
              description="No log entries match the current filters. Connect a source on the Integrations page to start ingesting logs."
              icon={<ScrollText className="h-8 w-8" />}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-44">Time</TableHead>
                  <TableHead className="w-24">Severity</TableHead>
                  <TableHead className="w-40">Service</TableHead>
                  <TableHead className="w-28">Source</TableHead>
                  <TableHead>Message</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDate(l.timestamp)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={severityVariant(l.severity)}>
                        {l.severity}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {l.service}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {l.source}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {l.message}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {!loading && logs.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          Showing {logs.length} log {logs.length === 1 ? "entry" : "entries"}.
        </p>
      )}
    </div>
  );
}
