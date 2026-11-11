# AIOpsDesk frontend

Independent React UI for the local AIOpsDesk API. This folder contains application code rather than the original Vite starter page.

## Screens and components

| File | Purpose |
| --- | --- |
| `src/App.jsx` | Sign-in, service readiness, navigation and ticket analysis. |
| `src/History.jsx` | Role-filtered prediction history and saved result details. |
| `src/FeedbackForm.jsx` | Reviewed labels, reasons and confirmation before submission. |
| `src/FeedbackReview.jsx` | Feedback status and maintainer approval/rejection. |
| `src/PipelineConsole.jsx` | Maintainer job history, real stage progress, start/retry/cancel. |
| `src/PredictionExplanation.jsx` | Signed word/phrase contributions for each target. |
| `src/api.js` | JSON requests, bearer tokens, timeouts and user-facing errors. |
| `src/App.css`, `src/index.css` | Responsive layout, contrast, focus and labelled statuses. |

The browser communicates only through REST. It contains no training or model-loading code. Sessions are held in memory, so refreshing requires another sign-in.

## Configuration

`public/config.js` sets `window.AIOPS_CONFIG.API_BASE_URL`, normally `/api`. In Docker, Nginx forwards `/api/` to `api:8000`. During development, `vite.config.js` proxies the same prefix to `http://127.0.0.1:8000`.

## Local development

Run from the repository root:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Vite uses **127.0.0.1:3002** with a strict port. Stop the Docker frontend first if using that port for development; keep the API/model running. Stop Vite before starting the Docker frontend again. Do not terminate an unrelated process to free the port.

## Checks and production build

```bash
npm --prefix frontend run lint
npm --prefix frontend run build
```

`package-lock.json` pins the npm dependency resolution. Generated `node_modules/` and `dist/` are ignored by Git. The frontend Dockerfile performs its own npm install/build and serves the output with nonroot Nginx; see `../deploy/docker/Dockerfile.frontend`.

For complete setup, measured results and the user manual, see the [main README](../README.md).
