import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// The backend stores timestamps in UTC but may serialize them without a
// timezone marker (a "naive" ISO string). Browsers parse those as LOCAL time,
// which shifts everything by the user's UTC offset. Mark such strings as UTC so
// toLocaleString converts them back to the viewer's local time correctly.
function parseTimestamp(value: string): Date {
  let v = value;
  if (v.includes(":") && !/(z|[+-]\d{2}:?\d{2})$/i.test(v)) {
    v = v.replace(" ", "T") + "Z";
  }
  return new Date(v);
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = parseTimestamp(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(value?: string | null): string {
  if (!value) return "—";
  const d = parseTimestamp(value);
  if (isNaN(d.getTime())) return value;
  const diff = Date.now() - d.getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.round(hr / 24);
  return `${days}d ago`;
}
