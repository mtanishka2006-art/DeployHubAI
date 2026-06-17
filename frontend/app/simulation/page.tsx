"use client";

import * as React from "react";
import {
  FlaskConical,
  Loader2,
  Zap,
  Clock,
  GitBranch,
  ListOrdered,
  AlertTriangle,
  Play,
} from "lucide-react";
import { getSimulationScenarios, runSimulation } from "@/lib/api";
import type {
  ScenarioInfo,
  ScenarioType,
  SimulationResult,
} from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Loading, ErrorState, EmptyState } from "@/components/states";

const impactVariant = (impact: string) => {
  switch (impact) {
    case "critical":
      return "danger" as const;
    case "high":
      return "warning" as const;
    case "moderate":
      return "info" as const;
    default:
      return "muted" as const;
  }
};

export default function SimulationPage() {
  const [scenarios, setScenarios] = React.useState<ScenarioInfo[]>([]);
  const [scenario, setScenario] = React.useState<ScenarioType>(
    "aws_region_outage"
  );
  const [target, setTarget] = React.useState(""); // "" = use default
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<SimulationResult | null>(null);

  // Load the scenario catalog (with valid targets) from the backend.
  React.useEffect(() => {
    getSimulationScenarios()
      .then((s) => {
        setScenarios(s);
        if (s.length && !s.some((x) => x.key === scenario)) {
          setScenario(s[0].key);
        }
      })
      .catch(() => {
        /* form still works; backend validates on submit */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = scenarios.find((s) => s.key === scenario);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const body: any = { scenario_type: scenario };
      if (target && current) {
        body[current.target_param] = target; // "region" or "target"
      }
      setResult(await runSimulation(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Disaster Simulation Center"
        description="Ask 'what if?' — trace dependencies, predict blast radius, estimate downtime, and generate a failover sequence before disaster strikes."
        icon={<FlaskConical className="h-5 w-5" />}
      />

      <div className="grid gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        {/* Control panel */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Play className="h-4 w-4" /> Configure Scenario
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={run} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  Failure scenario
                </label>
                <Select
                  value={scenario}
                  onChange={(e) => {
                    setScenario(e.target.value as ScenarioType);
                    setTarget("");
                  }}
                >
                  {scenarios.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">
                  {current?.target_param === "region" ? "Region" : "Target"}{" "}
                  (optional)
                </label>
                <Select
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  disabled={!current || current.targets.length === 0}
                >
                  <option value="">Default (auto-selected)</option>
                  {current?.targets.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </Select>
                <p className="text-[11px] text-muted-foreground">
                  {current && current.targets.length > 0
                    ? `Choose which ${current.target_param} to fail, or leave on Default.`
                    : "This scenario has a single fixed target."}
                </p>
              </div>
              {error && <ErrorState message={error} />}
              <Button type="submit" disabled={running} className="w-full">
                {running ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Simulating…
                  </>
                ) : (
                  <>
                    <Zap className="h-4 w-4" />
                    Run Simulation
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Results */}
        <div>
          {running ? (
            <Card>
              <CardContent>
                <Loading label="Tracing dependencies and computing blast radius…" />
              </CardContent>
            </Card>
          ) : !result ? (
            <Card className="flex h-full items-center justify-center">
              <CardContent className="py-16">
                <EmptyState
                  title="No simulation yet"
                  description="Pick a scenario and run it to see the predicted impact."
                  icon={<FlaskConical className="h-8 w-8" />}
                />
              </CardContent>
            </Card>
          ) : (
            <SimulationReport result={result} />
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-4">
        <div className="rounded-lg border border-border bg-background/40 p-2 text-primary">
          {icon}
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={`text-lg font-semibold ${tone || ""}`}>{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function SimulationReport({ result }: { result: SimulationResult }) {
  return (
    <div className="space-y-6">
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="flex items-start gap-3 py-4">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
          <p className="text-sm">{result.summary}</p>
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat
          icon={<Zap className="h-4 w-4" />}
          label="Blast radius"
          value={`${result.blast_radius.service_count} services`}
          tone={
            result.blast_radius.severity === "critical"
              ? "text-red-400"
              : "text-amber-400"
          }
        />
        <Stat
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Severity"
          value={result.blast_radius.severity}
        />
        <Stat
          icon={<Clock className="h-4 w-4" />}
          label="Est. downtime"
          value={`${result.estimated_downtime_minutes} min`}
        />
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Blast Radius</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            {result.blast_radius.description}
          </p>
          <div className="flex flex-wrap gap-2">
            {result.affected_services.map((s) => (
              <Badge key={s.service} variant={impactVariant(s.impact)}>
                {s.service} · {s.impact}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <ListOrdered className="h-4 w-4" /> Failover Sequence
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-2">
              {result.failover_sequence.map((step) => (
                <li key={step.step} className="flex items-start gap-3 text-sm">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/15 text-xs font-bold text-primary">
                    {step.step}
                  </span>
                  <span className="flex-1">{step.action}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    ~{step.eta_minutes}m
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Recovery Strategy</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {result.recovery_strategy.map((s, idx) => (
                <li key={idx} className="flex gap-2 text-sm">
                  <span className="text-primary">▸</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      {result.dependency_trace.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <GitBranch className="h-4 w-4" /> Dependency Trace
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2 font-mono text-xs">
              {result.dependency_trace.slice(0, 30).map((d, idx) => (
                <span
                  key={idx}
                  className="rounded border border-border bg-background/40 px-2 py-1 text-muted-foreground"
                >
                  {d.from}
                  <span className="mx-1 text-primary">
                    —{d.relation}→
                  </span>
                  {d.to}
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
