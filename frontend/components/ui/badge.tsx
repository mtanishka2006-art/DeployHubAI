import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary/15 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        success:
          "border-transparent bg-emerald-500/15 text-emerald-400",
        warning: "border-transparent bg-amber-500/15 text-amber-400",
        danger: "border-transparent bg-red-500/15 text-red-400",
        info: "border-transparent bg-sky-500/15 text-sky-400",
        muted: "border-transparent bg-muted text-muted-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

// Helpers mapping domain values to badge variants
type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

export function severityVariant(severity?: string): BadgeVariant {
  switch ((severity || "").toLowerCase()) {
    case "critical":
    case "sev1":
    case "p1":
      return "danger";
    case "high":
    case "sev2":
    case "p2":
      return "warning";
    case "medium":
    case "sev3":
    case "p3":
      return "info";
    case "low":
    case "sev4":
    case "p4":
      return "muted";
    default:
      return "secondary";
  }
}

export function statusVariant(status?: string): BadgeVariant {
  const s = (status || "").toLowerCase();
  if (
    ["healthy", "success", "succeeded", "resolved", "ok", "active", "ready", "online", "completed", "passed", "in_sync"].some(
      (x) => s.includes(x)
    )
  )
    return "success";
  if (
    ["degraded", "warning", "pending", "running", "in_progress", "investigating", "warn", "lagging"].some((x) =>
      s.includes(x)
    )
  )
    return "warning";
  if (
    ["failed", "failure", "critical", "down", "error", "open", "offline", "outage"].some((x) =>
      s.includes(x)
    )
  )
    return "danger";
  return "secondary";
}
