import * as React from "react";

export function PageHeader({
  title,
  description,
  icon,
  actions,
}: {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        {icon && (
          <div className="mt-0.5 rounded-lg border border-border bg-card p-2 text-primary">
            {icon}
          </div>
        )}
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            {title}
          </h1>
          {description && (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
