"use client";

import * as React from "react";
import {
  Workflow,
  Github,
  Gitlab,
  Cog,
  Cloud,
  GitBranch,
  Zap,
  FileCode2,
  ArrowRight,
} from "lucide-react";
import { getPipelines } from "@/lib/api";
import type { Pipeline } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Badge, statusVariant } from "@/components/ui/badge";
import { Select } from "@/components/ui/input";
import { Loading, ErrorState, EmptyState } from "@/components/states";

const PROVIDER_META: Record<string, { label: string; icon: typeof Workflow }> = {
  github_actions: { label: "GitHub Actions", icon: Github },
  gitlab_ci: { label: "GitLab CI", icon: Gitlab },
  jenkins: { label: "Jenkins", icon: Cog },
  azure_pipelines: { label: "Azure Pipelines", icon: Cloud },
  circleci: { label: "CircleCI", icon: Workflow },
  bitbucket: { label: "Bitbucket", icon: GitBranch },
  travis: { label: "Travis CI", icon: Workflow },
};

function titleCase(s: string): string {
  return s
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function PipelinesPage() {
  const [pipelines, setPipelines] = React.useState<Pipeline[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [provider, setProvider] = React.useState("all");
  const [status, setStatus] = React.useState("all");

  React.useEffect(() => {
    getPipelines()
      .then((rows) => {
        // De-dup identical pipelines (same provider + file + name + app) so a
        // duplicated source row never shows up twice.
        const seen = new Set<string>();
        setPipelines(
          rows.filter((p) => {
            const key = `${p.provider}|${p.app_name}|${p.file_path}|${p.name}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          })
        );
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load pipelines")
      );
  }, []);

  const providers = React.useMemo(
    () => Array.from(new Set((pipelines || []).map((p) => p.provider))).sort(),
    [pipelines]
  );
  const statuses = React.useMemo(
    () => Array.from(new Set((pipelines || []).map((p) => p.status))).sort(),
    [pipelines]
  );

  const filtered = React.useMemo(
    () =>
      (pipelines || []).filter(
        (p) =>
          (provider === "all" || p.provider === provider) &&
          (status === "all" || p.status === status)
      ),
    [pipelines, provider, status]
  );

  return (
    <div>
      <PageHeader
        title="Pipelines"
        description="CI/CD pipelines detected in connected sources — workflows, stages, and triggers."
        icon={<Workflow className="h-5 w-5" />}
      />

      {error && <ErrorState message={error} className="mb-6" />}

      {pipelines === null ? (
        <Loading label="Loading pipelines…" />
      ) : pipelines.length === 0 ? (
        <EmptyState
          title="No pipelines detected"
          description="None of the connected sources define CI/CD pipelines (e.g. .github/workflows, Jenkinsfile, .gitlab-ci.yml). Connect a repo that contains them and they'll appear here."
          icon={<Workflow className="h-8 w-8" />}
        />
      ) : (
        <div className="space-y-5">
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-52">
              <Select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="all">All providers</option>
                {providers.map((pv) => (
                  <option key={pv} value={pv}>
                    {PROVIDER_META[pv]?.label || pv}
                  </option>
                ))}
              </Select>
            </div>
            <div className="w-44">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="all">All statuses</option>
                {statuses.map((st) => (
                  <option key={st} value={st}>
                    {titleCase(st)}
                  </option>
                ))}
              </Select>
            </div>
            <p className="ml-auto text-xs text-muted-foreground">
              {filtered.length} of {pipelines.length} pipeline
              {pipelines.length === 1 ? "" : "s"}
            </p>
          </div>

          {/* Pipeline cards */}
          {filtered.length === 0 ? (
            <EmptyState
              title="No pipelines match the filters"
              description="Adjust the provider or status filters to see more pipelines."
              icon={<Workflow className="h-8 w-8" />}
            />
          ) : (
            <div className="space-y-4">
              {filtered.map((p) => {
                const meta = PROVIDER_META[p.provider] || {
                  label: p.provider,
                  icon: Workflow,
                };
                const Icon = meta.icon;
                return (
                  <Card key={p.id} className="p-5">
                    {/* Header row */}
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <h3 className="flex items-center gap-2 text-lg font-semibold">
                          <Icon className="h-4 w-4 shrink-0 text-primary" />
                          <span className="truncate">{p.name}</span>
                        </h3>
                        <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                          <FileCode2 className="h-3 w-3 shrink-0" />
                          <span className="truncate">{p.file_path}</span>
                          <span className="text-muted-foreground/50">·</span>
                          <span className="truncate">{p.app_name}</span>
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <Badge variant={statusVariant(p.status)}>
                          {titleCase(p.status)}
                        </Badge>
                        <span className="hidden text-sm text-muted-foreground sm:inline">
                          {meta.label}
                        </span>
                      </div>
                    </div>

                    {/* Stage flow */}
                    {p.stages.length > 0 ? (
                      <div className="mt-4 flex flex-wrap items-stretch gap-2">
                        {p.stages.map((s, i) => (
                          <React.Fragment key={`${s}-${i}`}>
                            {i > 0 && (
                              <ArrowRight className="h-4 w-4 self-center text-muted-foreground/40" />
                            )}
                            <div className="min-w-[112px] rounded-lg border border-border bg-background/40 px-4 py-2.5 text-center">
                              <div className="truncate text-sm font-medium">
                                {s}
                              </div>
                            </div>
                          </React.Fragment>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-4 text-xs text-muted-foreground">
                        No stages detected in this pipeline definition.
                      </p>
                    )}

                    {/* Triggers */}
                    {p.triggers.length > 0 && (
                      <div className="mt-4 flex flex-wrap items-center gap-1.5">
                        <span className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
                          <Zap className="h-3 w-3" /> Triggers
                        </span>
                        {p.triggers.map((t) => (
                          <Badge key={t} variant="muted">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
