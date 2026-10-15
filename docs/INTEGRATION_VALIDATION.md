# Main integration validation — 2026-10-15

Camera validation and incident review have been integrated with the production-capacity changes already merged in PR #5. CI retains all six jobs, both sets of AI test dependencies, capacity and validation lint coverage, and Windows webcam regressions. Feature branch pushes use `feat/**`. Windows instructions now download `main`.

## Local verification

| Check | Result |
| --- | --- |
| Backend suite with disposable PostgreSQL, Redis and RabbitMQ | 110 passed; one optional synthetic MediaMTX relay smoke skipped because no test relay URL was configured |
| AI suite, including the checksum-pinned trial ONNX model smoke checks | 88 passed |
| Chromium browser regressions | 15 passed |
| Configured backend, capacity-tool and AI lint | Passed |
| Frontend TypeScript and production build | Passed |
| Production frontend Docker image | Built successfully |
| Production Compose validation | Passed, including private services, read-only model mounts and explicit GPU allocation |
| Prometheus configuration and capacity rule tests | Passed |
| Capacity load-script syntax and worker import smoke | Passed; no load test or model startup performed |
| CI workflow structure | Valid YAML, no duplicate keys, all six jobs retained |

The cloud Docker build used the environment's proxy configuration and a temporary build-secret CA certificate. Local verification used Linux, Python 3.12 and Node 24; it does not establish the outcome of GitHub Actions or physical Windows webcam execution. Existing dependency deprecation and frontend bundle-size warnings remain.

## Remaining pilot evidence

This integration does not establish PPE accuracy or a supported camera count. The user's webcam report establishes capture only; the local PPE preview and independent labeled-image evaluation remain pending. Production sizing still requires compatible production model weights, chosen hardware and an integrated camera pilot. Production GPU runtime, site media/TLS, notification-provider load and backup/restore validation remain separate deployment gates.

See [camera evidence](REAL_CAMERA_VALIDATION_STATUS.md), [incident review](INCIDENT_REVIEW.md) and [measured capacity planning](PRODUCTION_CAPACITY.md).
