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
} from "lucide-react";
import { getPipelines } from "@/lib/api";
import type { Pipeline } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

export default function PipelinesPage() {
  const [pipelines, setPipelines] = React.useState<Pipeline[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    getPipelines()
      .then(setPipelines)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load pipelines")
      );
  }, []);

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
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            {pipelines.length} pipeline{pipelines.length === 1 ? "" : "s"} across
            connected sources.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {pipelines.map((p) => {
              const meta = PROVIDER_META[p.provider] || {
                label: p.provider,
                icon: Workflow,
              };
              const Icon = meta.icon;
              return (
                <Card key={p.id}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Icon className="h-4 w-4 text-primary" />
                        {p.name}
                      </CardTitle>
                      <Badge variant="info">{meta.label}</Badge>
                    </div>
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                      <FileCode2 className="h-3 w-3" />
                      {p.file_path}
                      <span className="text-muted-foreground/60">·</span>
                      {p.app_name}
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-3 text-sm">
                    {p.triggers.length > 0 && (
                      <div>
                        <span className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                          <Zap className="h-3 w-3" /> Triggers
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {p.triggers.map((t) => (
                            <Badge key={t} variant="muted">
                              {t}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    {p.stages.length > 0 && (
                      <div>
                        <span className="mb-1 block text-xs font-medium text-muted-foreground">
                          Stages / Jobs ({p.stages.length})
                        </span>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {p.stages.map((s, i) => (
                            <React.Fragment key={`${s}-${i}`}>
                              {i > 0 && (
                                <span className="text-muted-foreground/50">→</span>
                              )}
                              <span className="rounded-md border border-border bg-background/40 px-2 py-1 text-xs">
                                {s}
                              </span>
                            </React.Fragment>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
