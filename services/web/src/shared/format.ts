// Formatting helpers shared by the server and the browser dashboard.

export type Theme = "preview" | "staging" | "production" | "local";

/** Map an environment name to the colour theme of the dashboard banner. */
export function themeFor(environment: string): Theme {
  const env = environment.toLowerCase();
  if (env === "production" || env === "prod") return "production";
  if (env === "staging" || env === "stage") return "staging";
  if (env.startsWith("pr-") || env.startsWith("preview")) return "preview";
  return "local";
}

/** Shorten a commit SHA for display. Unknown values pass through unchanged. */
export function shortSha(sha: string | undefined): string {
  if (!sha || sha === "unknown") return "unknown";
  return /^[0-9a-f]{12,}$/i.test(sha) ? sha.slice(0, 7) : sha;
}

/** Render an uptime in seconds as a compact human readable string. */
export function formatUptime(seconds: number | undefined): string {
  if (seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return "n/a";
  const s = Math.floor(seconds);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${s % 60}s`;
  return `${s}s`;
}

/** True when every known commit is identical, proving one build runs everywhere. */
export function sameCommit(commits: (string | undefined)[]): boolean {
  const known = commits.filter((c): c is string => !!c && c !== "unknown");
  return known.length > 1 && known.every((c) => c === known[0]);
}
