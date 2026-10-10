// Runtime configuration. Build metadata is baked into the image as env vars,
// runtime settings change per environment while the image stays identical.

export interface Config {
  port: number;
  environment: string;
  apiUrl: string;
  repoUrl: string;
  statusPageUrl: string;
  imageRef: string;
  version: string;
  commit: string;
  buildTime: string;
  startedAt: Date;
}

function trimSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  return {
    port: Number(env.PORT ?? 8082),
    environment: env.APP_ENV ?? "local",
    apiUrl: trimSlash(env.API_URL ?? "http://localhost:8080"),
    repoUrl: trimSlash(env.REPO_URL ?? ""),
    statusPageUrl: trimSlash(env.STATUS_PAGE_URL ?? ""),
    imageRef: env.IMAGE_REF ?? "",
    version: env.APP_VERSION ?? "dev",
    commit: env.GIT_SHA ?? "unknown",
    buildTime: env.BUILD_TIME ?? "unknown",
    startedAt: new Date(),
  };
}

export function versionInfo(cfg: Config): Record<string, unknown> {
  const info: Record<string, unknown> = {
    service: "web",
    version: cfg.version,
    commit: cfg.commit,
    buildTime: cfg.buildTime,
    environment: cfg.environment,
    startedAt: cfg.startedAt.toISOString(),
    uptimeSeconds: Math.floor((Date.now() - cfg.startedAt.getTime()) / 1000),
  };
  if (cfg.imageRef) info.imageRef = cfg.imageRef;
  if (cfg.repoUrl && cfg.commit !== "unknown") info.commitUrl = `${cfg.repoUrl}/commit/${cfg.commit}`;
  return info;
}
