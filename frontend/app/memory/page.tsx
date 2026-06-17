"use client";

import * as React from "react";
import { BrainCircuit, Search, Loader2, History } from "lucide-react";
import { memorySearch } from "@/lib/api";
import type { MemoryResult } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Loading, ErrorState, EmptyState } from "@/components/states";
import { formatDate } from "@/lib/utils";

const COLLECTIONS = [
  { value: "incident_memory", label: "Incidents" },
  { value: "recovery_memory", label: "Recoveries" },
  { value: "deployment_memory", label: "Deployment failures" },
  { value: "dr_memory", label: "DR incidents" },
];

const EXAMPLES = [
  "checkout 500 errors after a deploy",
  "database connection pool exhausted",
  "AWS region failover",
  "kubernetes pods OOMKilled",
];

export default function MemoryPage() {
  const [query, setQuery] = React.useState("");
  const [collection, setCollection] = React.useState("incident_memory");
  const [results, setResults] = React.useState<MemoryResult[] | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const run = React.useCallback(
    async (q: string) => {
      if (!q.trim()) return;
      setLoading(true);
      setError(null);
      try {
        const res = await memorySearch({ query: q, collection, k: 8 });
        setResults(res.results);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [collection]
  );

  return (
    <div>
      <PageHeader
        title="Infrastructure Memory"
        description="Semantic RAG over historical incidents, root causes, and recovery playbooks. Agents learn from what resolved similar problems before."
        icon={<BrainCircuit className="h-5 w-5" />}
      />

      <Card className="mb-6">
        <CardContent className="pt-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(query);
            }}
            className="flex flex-col gap-3 sm:flex-row"
          >
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Describe a symptom or incident…"
                className="pl-9"
              />
            </div>
            <Select
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              className="sm:w-56"
            >
              {COLLECTIONS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
            <Button type="submit" disabled={loading || !query.trim()}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Search
            </Button>
          </form>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Try:</span>
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setQuery(ex);
                  run(ex);
                }}
                className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
              >
                {ex}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {error && <ErrorState message={error} className="mb-6" />}

      {loading ? (
        <Loading label="Searching memory…" />
      ) : results === null ? (
        <EmptyState
          title="Search the incident knowledge base"
          description="Enter a query above to retrieve semantically similar historical incidents and their resolutions."
          icon={<BrainCircuit className="h-8 w-8" />}
        />
      ) : results.length === 0 ? (
        <EmptyState title="No matches found" description="Try a broader query." />
      ) : (
        <div className="space-y-3">
          {results.map((r, idx) => {
            const pct = r.score <= 1 ? r.score * 100 : r.score;
            return (
              <Card key={r.id ?? idx}>
                <CardHeader className="flex flex-row items-start justify-between gap-3 pb-3">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <History className="h-4 w-4 text-primary" />
                    {r.title || "Historical record"}
                  </CardTitle>
                  <Badge variant="info">{pct.toFixed(0)}% match</Badge>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {r.summary && (
                    <p className="text-muted-foreground">{r.summary}</p>
                  )}
                  {r.root_cause && (
                    <p>
                      <span className="font-medium text-foreground">
                        Root cause:{" "}
                      </span>
                      <span className="text-muted-foreground">
                        {r.root_cause}
                      </span>
                    </p>
                  )}
                  {r.recovery_actions && r.recovery_actions.length > 0 && (
                    <div>
                      <span className="font-medium">Recovery actions:</span>
                      <ul className="mt-1 list-inside list-disc text-muted-foreground">
                        {r.recovery_actions.map((a, i) => (
                          <li key={i}>{a}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {r.outcome && (
                    <p className="text-emerald-400">{r.outcome}</p>
                  )}
                  {r.occurred_at && (
                    <p className="text-xs text-muted-foreground">
                      {formatDate(r.occurred_at)}
                    </p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
