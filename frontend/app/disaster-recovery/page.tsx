"use client";

import * as React from "react";
import {
  ShieldCheck,
  RefreshCw,
  Database,
  GitBranch,
  Server,
  Activity,
} from "lucide-react";
import { getDrEvents, getDrStatus } from "@/lib/api";
import type { DrEvent, DrStatus } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Gauge } from "@/components/gauge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge, statusVariant } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Loading, ErrorState, EmptyState } from "@/components/states";
import { formatDate } from "@/lib/utils";

export default function DisasterRecoveryPage() {
  const [status, setStatus] = React.useState<DrStatus | null>(null);
  const [events, setEvents] = React.useState<DrEvent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, e] = await Promise.all([
        getDrStatus(),
        getDrEvents({ limit: 50 }),
      ]);
      setStatus(s);
      setEvents(e);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load DR data");
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
        title="Disaster Recovery Center"
        description="Backups, replication health, failover readiness, and DR event log."
        icon={<ShieldCheck className="h-5 w-5" />}
        actions={
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        }
      />

      {error && <ErrorState message={error} className="mb-6" />}

      {loading && !status ? (
        <Loading label="Assessing disaster recovery readiness…" />
      ) : status ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>DR Readiness</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col items-center">
                {status.dr_score == null ||
                status.readiness === "not_measured" ? (
                  <div className="flex flex-col items-center py-6 text-center">
                    <span className="text-3xl font-bold text-muted-foreground">
                      N/A
                    </span>
                    <p className="mt-2 max-w-[15rem] text-xs text-muted-foreground">
                      DR readiness needs backup / replication / failover data —
                      the connected source doesn’t provide it.
                    </p>
                  </div>
                ) : (
                  <>
                    <Gauge value={status.dr_score} label="readiness" />
                    <Badge
                      variant={statusVariant(status.readiness)}
                      className="mt-3 capitalize"
                    >
                      {status.readiness}
                    </Badge>
                  </>
                )}
              </CardContent>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Database className="h-4 w-4" /> Backups
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {status.backups.length === 0 ? (
                  <EmptyState title="No backup systems reported" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>System</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Last Backup</TableHead>
                        <TableHead>RPO</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {status.backups.map((b, i) => (
                        <TableRow key={`${b.system}-${i}`}>
                          <TableCell className="font-medium">
                            {b.system}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={statusVariant(b.status)}
                              className="capitalize"
                            >
                              {b.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {formatDate(b.last_backup)}
                          </TableCell>
                          <TableCell className="tabular-nums">
                            {b.rpo_minutes}m
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <GitBranch className="h-4 w-4" /> Replication
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {status.replication.length === 0 ? (
                  <EmptyState title="No replication links" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Source</TableHead>
                        <TableHead>Target</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Lag</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {status.replication.map((r, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-medium">
                            {r.source}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {r.target}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={statusVariant(r.status)}
                              className="capitalize"
                            >
                              {r.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="tabular-nums">
                            {r.lag_seconds}s
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
                  <Server className="h-4 w-4" /> Failover Targets
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {status.failovers.length === 0 ? (
                  <EmptyState title="No failover targets" />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Service</TableHead>
                        <TableHead>Region</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Last Tested</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {status.failovers.map((f, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-medium">
                            {f.service}
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {f.region}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={statusVariant(f.status)}
                              className="capitalize"
                            >
                              {f.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {formatDate(f.last_tested)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-4 w-4" /> DR Event Log
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {events.length === 0 ? (
                <EmptyState title="No DR events recorded" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Event</TableHead>
                      <TableHead>Service</TableHead>
                      <TableHead>Region</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Detail</TableHead>
                      <TableHead>When</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {events.map((e) => (
                      <TableRow key={e.id}>
                        <TableCell className="font-medium capitalize">
                          {e.event_type?.replace(/_/g, " ")}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {e.service}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {e.region}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={statusVariant(e.status)}
                            className="capitalize"
                          >
                            {e.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-xs text-xs text-muted-foreground">
                          {e.detail || "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDate(e.timestamp)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
