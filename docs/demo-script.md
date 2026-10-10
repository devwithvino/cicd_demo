# Demo script (about 3 minutes)

A screen recording for prospective clients. It shows a change travelling from a pull request to production, a broken release being caught and undone, and the evidence behind it.

## Before recording (10 minutes ahead)

1. **Wake the free instances.** Open the production and staging apps and the status page once, so nothing shows a cold start on camera:
   - https://shipyard-web-production.onrender.com
   - https://shipyard-web-staging.onrender.com
   - https://devwithvino.github.io/cicd_demo/
2. **Start the rollback demo on staging** about 5 minutes before recording, so its result is ready to show: Actions, **demo-failure**, Run workflow, target `staging`.
3. **Prepare a small pull request**, for example a wording change on the dashboard, with a Conventional Commit title such as `feat: welcome message on the dashboard`. Open it so its preview is ready.
4. Open these tabs in order: the pull request, the Actions run of the last delivery, Slack, the demo-failure run, the incident issue it opened, Sentry, the latest release, the status page.

## Script

| Time | Screen | Say |
|---|---|---|
| 0:00 | Production app | "This is a small app with three services. The app is simple on purpose: what I want to show you is how changes reach it." |
| 0:15 | Pull request | "Every change starts as a pull request. Within minutes it has been linted, tested, scanned for secrets and vulnerabilities, and it has its own live copy." Click the preview link in the bot comment. |
| 0:35 | Preview app (purple banner) | "This is that change, running on its own environment, with its own data. It disappears when the pull request closes." |
| 0:45 | Delivery run (graph view) | "Merging starts the delivery. The app is built once, scanned and signed, then the same images go to staging and to a Kubernetes cluster in parallel." Point at the stages. |
| 1:05 | Slack approval message | "When it reaches production, the pipeline stops and asks a person. This message has the button." Click **Review and approve**. |
| 1:20 | Delivery run, finished | "Production gets the identical images that passed staging. Not rebuilt, the same bytes. Then it checks itself again, and asks Sentry if the new version caused any errors." |
| 1:40 | demo-failure run | "What if a release is broken? Here I shipped one on purpose. Every health check was green, so the hosting platform was happy. The pipeline's own test tried to use the app, failed, and put the previous version back." |
| 2:00 | Incident issue | "It restored service in under a minute and wrote this incident report itself, with a timeline." |
| 2:10 | Sentry | "The error was also captured in Sentry, tagged with the exact release that caused it." |
| 2:20 | Latest GitHub Release | "Every release ships with its parts list and a signed record of where it was built. Anyone can verify that with one command." |
| 2:35 | Status page | "And this is the page I would share with your team: live health, and the four industry standard delivery metrics, measured from real runs." |
| 2:50 | Status page | "All of this runs on free tiers. I can set up the same pipeline for your stack." |

## Tips

- Record at 1080p with the browser zoomed to 110 or 125 percent so text is readable.
- Keep the mouse still when talking about something that is not on screen.
- If an instance cold starts on camera, say so: "free hosting sleeps when idle; the page tells you while it wakes". It is honest and shows the dashboard handles it.
- After recording, close the demo pull request so its preview is cleaned up.
