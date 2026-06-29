"use client";

import * as React from "react";
import {
  Plug,
  Github,
  Cloud,
  CloudCog,
  ClipboardList,
  BellRing,
  Activity,
  Boxes,
  Loader2,
  RefreshCw,
  Trash2,
  X,
  CheckCircle2,
  Radio,
  Upload,
  GitBranch,
  Globe,
} from "lucide-react";
import {
  getAvailableConnectors,
  getConnectedApps,
  connectConnector,
  syncConnector,
  deleteConnector,
  getConnectorEvents,
  importProject,
} from "@/lib/api";
import type {
  AvailableConnector,
  ConnectedApp,
  ConnectorEvent,
} from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, severityVariant, statusVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Loading, ErrorState, EmptyState } from "@/components/states";
import { timeAgo } from "@/lib/utils";

function iconFor(appType: string) {
  switch (appType) {
    case "github_actions":
      return Github;
    case "aws":
      return Cloud;
    case "gcp":
      return CloudCog;
    case "jira":
      return ClipboardList;
    case "pagerduty":
      return BellRing;
    case "datadog":
      return Activity;
    case "kubernetes":
      return Boxes;
    case "project_import":
      return Upload;
    case "git_repo":
      return GitBranch;
    case "website":
      return Globe;
    default:
      return Plug;
  }
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "connected"
      ? "bg-emerald-500"
      : status === "error"
      ? "bg-red-500"
      : "bg-zinc-500";
  return (
    <span className="relative flex h-2.5 w-2.5">
      {status === "connected" && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
      )}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${color}`} />
    </span>
  );
}

export default function IntegrationsPage() {
  const [available, setAvailable] = React.useState<AvailableConnector[]>([]);
  const [apps, setApps] = React.useState<ConnectedApp[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [connectFor, setConnectFor] =
    React.useState<AvailableConnector | null>(null);
  const [busyId, setBusyId] = React.useState<number | null>(null);
  const [importing, setImporting] = React.useState(false);
  const [replaceData, setReplaceData] = React.useState(true);
  const [feedApp, setFeedApp] = React.useState<ConnectedApp | null>(null);
  const [feed, setFeed] = React.useState<ConnectorEvent[]>([]);

  const byType = React.useMemo(() => {
    const m: Record<string, ConnectedApp> = {};
    apps.forEach((a) => (m[a.app_type] = a));
    return m;
  }, [apps]);

  const load = React.useCallback(async () => {
    try {
      const [av, connected] = await Promise.all([
        getAvailableConnectors(),
        getConnectedApps(),
      ]);
      setAvailable(av);
      setApps(connected);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  // Auto-refresh connected apps + open feed every 30s.
  React.useEffect(() => {
    const t = setInterval(() => {
      getConnectedApps().then(setApps).catch(() => {});
      if (feedApp) getConnectorEvents(feedApp.id, 5).then(setFeed).catch(() => {});
    }, 30000);
    return () => clearInterval(t);
  }, [feedApp]);

  const openFeed = async (app: ConnectedApp) => {
    setFeedApp(app);
    try {
      setFeed(await getConnectorEvents(app.id, 5));
    } catch {
      setFeed([]);
    }
  };

  const handleImport = async (file?: File | null) => {
    if (!file) return;
    setImporting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await importProject(file, replaceData);
      setNotice(
        `Imported ${res.app_name}: ${res.commits} commits → ${res.deployments} ` +
          `deployments, ${res.incidents} incidents, ${res.pipelines ?? 0} pipelines ` +
          `across ${res.services.length} services.` +
          (replaceData ? " Dashboards now show only this app." : "")
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const doSync = async (app: ConnectedApp) => {
    setBusyId(app.id);
    setNotice(null);
    try {
      const res = await syncConnector(app.id);
      setNotice(`${app.name}: ${res.message}`);
      await load();
      if (feedApp?.id === app.id) openFeed(app);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setBusyId(null);
    }
  };

  const doDisconnect = async (app: ConnectedApp) => {
    setBusyId(app.id);
    try {
      await deleteConnector(app.id);
      if (feedApp?.id === app.id) setFeedApp(null);
      setNotice(`${app.name} disconnected.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="App Connector Hub"
        description="Connect real third-party tools. Once connected, their live data flows through the pipeline into every dashboard."
        icon={<Plug className="h-5 w-5" />}
      />

      {notice && (
        <div className="mb-4 flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300">
          <CheckCircle2 className="h-4 w-4" /> {notice}
        </div>
      )}
      {error && <ErrorState message={error} className="mb-4" />}

      {loading ? (
        <Loading label="Loading integrations…" />
      ) : (
        <div className="space-y-8">
          {/* Available integrations */}
          <div>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Available Integrations
            </h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {available.map((conn) => {
                const Icon = iconFor(conn.app_type);
                const connected = byType[conn.app_type];
                return (
                  <Card key={conn.app_type} className="flex flex-col">
                    <CardContent className="flex flex-1 flex-col gap-3 p-5">
                      <div className="flex items-start gap-3">
                        <div className="rounded-lg border border-border bg-background/50 p-2.5 text-primary">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="font-semibold">{conn.label}</h3>
                            {connected && (
                              <Badge variant="success">Connected</Badge>
                            )}
                            {!conn.live_supported && (
                              <Badge variant="muted">soon</Badge>
                            )}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {conn.description}
                          </p>
                        </div>
                      </div>
                      <div className="mt-auto flex flex-wrap gap-2 pt-2">
                        {conn.upload ? (
                          <div className="w-full space-y-2">
                            <label className="flex cursor-pointer items-center gap-2 text-[11px] text-muted-foreground">
                              <input
                                type="checkbox"
                                checked={replaceData}
                                onChange={(e) => setReplaceData(e.target.checked)}
                                className="h-3.5 w-3.5 accent-sky-500"
                              />
                              Replace existing data (show only this app)
                            </label>
                            <div className="flex flex-wrap gap-2">
                              <label className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow shadow-primary/20 hover:bg-primary/90">
                                <input
                                  type="file"
                                  accept=".zip"
                                  className="hidden"
                                  disabled={importing}
                                  onChange={(e) =>
                                    handleImport(e.target.files?.[0])
                                  }
                                />
                                {importing ? (
                                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Upload className="h-3.5 w-3.5" />
                                )}
                                {connected ? "Re-upload .zip" : "Upload .zip"}
                              </label>
                              {connected && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => doDisconnect(connected)}
                                  disabled={busyId === connected.id}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                  Remove
                                </Button>
                              )}
                            </div>
                          </div>
                        ) : connected ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => doSync(connected)}
                              disabled={busyId === connected.id}
                            >
                              {busyId === connected.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <RefreshCw className="h-3.5 w-3.5" />
                              )}
                              Sync Now
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => doDisconnect(connected)}
                              disabled={busyId === connected.id}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              Disconnect
                            </Button>
                          </>
                        ) : (
                          <Button size="sm" onClick={() => setConnectFor(conn)}>
                            <Plug className="h-3.5 w-3.5" />
                            Connect
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>

          {/* Connected apps table */}
          <div>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Connected Apps
            </h2>
            <Card>
              <CardContent className="p-0">
                {apps.length === 0 ? (
                  <EmptyState
                    title="No apps connected yet"
                    description="Connect an integration above to start pulling live data."
                    icon={<Plug className="h-8 w-8" />}
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Last Synced</TableHead>
                        <TableHead>Events</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {apps.map((a) => (
                        <TableRow
                          key={a.id}
                          className="cursor-pointer"
                          onClick={() => openFeed(a)}
                        >
                          <TableCell className="font-medium">{a.name}</TableCell>
                          <TableCell>
                            <span className="flex items-center gap-2">
                              <StatusDot status={a.status} />
                              <span className="capitalize text-muted-foreground">
                                {a.status}
                              </span>
                            </span>
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {a.last_synced_at
                              ? timeAgo(a.last_synced_at)
                              : "never"}
                          </TableCell>
                          <TableCell className="tabular-nums">
                            {a.events_ingested}
                          </TableCell>
                          <TableCell
                            className="text-right"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => doSync(a)}
                              disabled={busyId === a.id}
                            >
                              {busyId === a.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <RefreshCw className="h-3.5 w-3.5" />
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => doDisconnect(a)}
                              disabled={busyId === a.id}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Live feed */}
          {feedApp && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Radio className="h-4 w-4 text-emerald-400" /> Live feed —{" "}
                  {feedApp.name}
                  <span className="text-xs font-normal text-muted-foreground">
                    (
                    {feedApp.last_synced_at
                      ? `synced ${timeAgo(feedApp.last_synced_at)}`
                      : "not synced"}
                    , auto-refresh 30s)
                  </span>
                </CardTitle>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setFeedApp(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </CardHeader>
              <CardContent className="space-y-2">
                {feed.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No events ingested yet — try “Sync Now”.
                  </p>
                ) : (
                  feed.map((e) => (
                    <div
                      key={e.id}
                      className="flex items-center justify-between gap-3 rounded-md border border-border bg-background/40 p-2.5 text-sm"
                    >
                      <div className="flex items-center gap-2">
                        <Badge variant={severityVariant(e.severity)}>
                          {e.severity}
                        </Badge>
                        <span className="text-muted-foreground">
                          {e.event_type}
                        </span>
                        <span className="font-medium">{e.service}</span>
                      </div>
                      <span className="truncate text-xs text-muted-foreground">
                        {e.summary}
                      </span>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {connectFor && (
        <ConnectModal
          connector={connectFor}
          onClose={() => setConnectFor(null)}
          onConnected={(msg) => {
            setConnectFor(null);
            setNotice(msg);
            load();
          }}
        />
      )}
    </div>
  );
}

function ConnectModal({
  connector,
  onClose,
  onConnected,
}: {
  connector: AvailableConnector;
  onClose: () => void;
  onConnected: (msg: string) => void;
}) {
  const [creds, setCreds] = React.useState<Record<string, string>>({});
  const [name, setName] = React.useState(connector.label);
  const [interval, setIntervalSecs] = React.useState(60);
  // Default to MERGE so multiple integrations can be plugged in for one app and
  // their metrics show together. Check it for focus mode (show only this source).
  const [replace, setReplace] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const isGitRepo = connector.app_type === "git_repo";
  // Every source can be connected in "focus" mode — replacing prior data so the
  // dashboards reflect ONLY this source (defaults on). Uncheck to merge it
  // alongside existing data instead, so different sources don't overlap.
  const canReplace = true;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await connectConnector({
        app_type: connector.app_type,
        name,
        credentials: creds,
        polling_interval_seconds: interval,
        replace: canReplace ? replace : false,
      });
      onConnected(
        `${connector.label} connected — ${res.events_ingested} event(s) ingested.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <Card className="relative w-full max-w-lg">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Connect {connector.label}</CardTitle>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Display name
              </label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>

            {connector.fields.map((f) => (
              <div key={f.name} className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  {f.label}
                  {f.required && <span className="text-red-400"> *</span>}
                </label>
                <Input
                  type={f.type === "password" ? "password" : "text"}
                  placeholder={f.placeholder}
                  value={creds[f.name] || ""}
                  onChange={(e) =>
                    setCreds((c) => ({ ...c, [f.name]: e.target.value }))
                  }
                  required={f.required}
                  autoComplete="off"
                />
              </div>
            ))}

            {!isGitRepo && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Polling interval (seconds)
                </label>
                <Input
                  type="number"
                  min={15}
                  value={interval}
                  onChange={(e) => setIntervalSecs(Number(e.target.value) || 60)}
                />
              </div>
            )}

            {canReplace && (
              <label className="flex cursor-pointer items-center gap-2 text-[11px] text-muted-foreground">
                <input
                  type="checkbox"
                  checked={replace}
                  onChange={(e) => setReplace(e.target.checked)}
                  className="h-3.5 w-3.5 accent-sky-500"
                />
                Replace existing data (show only this source)
              </label>
            )}

            {!connector.live_supported && (
              <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
                Live sync for {connector.label} isn’t wired up yet — credentials
                are saved but no data is pulled.
              </p>
            )}
            {error && <ErrorState message={error} />}

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                Connect &amp; Sync
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
