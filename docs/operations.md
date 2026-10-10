# Operations guide: bringing Shipyard down and up

Shipyard runs in four places. Each one can be stopped and started on its own.

| Where | What runs there | Stop | Start |
|---|---|---|---|
| Render | staging and production (api, worker, web) and the shared Key Value | `platform` workflow, action `down` | `platform` workflow, action `up` |
| Render previews | one wired set per open pull request | close the pull request | open or update a pull request |
| Your laptop | the whole stack with Docker Compose | `docker compose down -v` | `docker compose up --build` |
| GitHub Actions (Kind) | a throwaway Kubernetes cluster per run | nothing to stop, it is deleted after every run | runs on every delivery and pull request |

## Pause and resume the hosted platform (recommended)

Use this when the demo is not needed for a while. It keeps every setting, image and secret, and costs nothing while paused.

**Down:** GitHub, Actions, **platform**, Run workflow, action `down`, scope `both` (or one environment).

- Suspends the api, worker and web services of the chosen environments.
- With scope `both`, also suspends the shared Key Value instance, after the services.
- When production is included, pauses the `nightly` and `sentry-slack` workflows so nothing reports false alarms.
- Production asks for the usual approval first.
- Slack gets a "platform down" message.

**Up:** the same workflow with action `up`.

- Resumes the Key Value instance first (scope `both`), then the services.
- Runs the smoke test in every environment it brought back. The first request wakes the free instances, which takes about a minute.
- Re enables the scheduled workflows.
- Slack gets a "platform up" message.

The same can be done by hand in the Render dashboard: select the services, then **Suspend** or **Resume**.

While the platform is down, the status page still loads (it is hosted on GitHub Pages) and shows the services as down. A delivery started while production is suspended fails its smoke test and stops before release, so bring the platform up first.

## Run it on your laptop

```bash
docker compose up --build
```

Open http://localhost:8080. Add `--profile observability` for Prometheus and Grafana. Stop and remove everything, including the local Key Value data:

```bash
docker compose --profile observability down -v
```

Free disk space used by images and build cache afterwards:

```bash
docker system prune -af
```

## Permanent teardown

Only for retiring the project. Each step is irreversible.

1. **Render:** in the dashboard, open the Blueprint and delete it together with its services and the Key Value instance. Or delete each service under Settings.
2. **Container images:** GitHub, your profile, Packages, delete `shipyard-api`, `shipyard-worker` and `shipyard-web`. Images that are still running somewhere stop being pullable.
3. **Status page:** repository Settings, Pages, unpublish the site.
4. **Sentry:** delete the `shipyard` project.
5. **Slack:** remove the incoming webhook app from the workspace.
6. **Secrets:** delete the Render API keys in Render and the repository and environment secrets in GitHub.
7. **Repository:** archive it (Settings, General, Archive) to keep the history read only, or delete it.

## Rebuild from scratch

Everything needed is in the repository.

1. **Render:** New, Blueprint, select the repository. `render.yaml` creates the six services and the Key Value instance. Blueprint auto sync can stay on, because the image tags in the Blueprint only move after a passing smoke test.
2. **GitHub environments:** `preview`, `staging` and `production` (production with a required reviewer and the `main` branch only).
3. **Environment variables:** in `staging` and `production`, set `RENDER_API_SERVICE_ID`, `RENDER_WORKER_SERVICE_ID`, `RENDER_WEB_SERVICE_ID`, `API_URL`, `WORKER_URL` and `WEB_URL` from the new services. In `preview`, set the three staging service IDs. Repository variable `RENDER_KV_ID` is the Key Value ID.
4. **Secrets:** `RENDER_API_KEY` in each of `preview`, `staging` and `production`. Repository secrets `SLACK_WEBHOOK_URL` and `SENTRY_AUTH_TOKEN`, repository variables `SENTRY_ORG`, `SENTRY_PROJECT` and `SENTRY_DSN`. Optional release App: `RELEASE_APP_CLIENT_ID` variable and `RELEASE_APP_PRIVATE_KEY` secret.
5. **Branch ruleset:** require pull requests and the checks `CI passed`, `Security passed` and `conventional commit title` on `main`.
6. **First delivery:** run the `deliver` workflow, approve production, and the platform is live.
