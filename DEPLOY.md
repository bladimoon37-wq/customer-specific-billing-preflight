# Deploy-ready V0

This build is prepared for a small public validation deployment.

## Important deployment changes
- Binds to `0.0.0.0` and reads `$PORT` from the hosting platform.
- No browser auto-open on the server.
- Browser sessions are isolated in memory so different visitors do not share rules/findings.
- Sessions expire after ~2 hours and are not persisted.
- Basic security headers are enabled.
- Request size is capped at 12 MiB by default (`MAX_UPLOAD_BYTES`).
- `/healthz` returns `200 ok`.

## Docker
```bash
docker build -t billing-preflight-v0 .
docker run --rm -p 8765:8765 billing-preflight-v0
```
Then open `http://localhost:8765`.

## Generic PaaS
Use the included Dockerfile. If the platform supplies a `PORT` environment variable, the app uses it automatically.

Start command if required:
```bash
python web_ui.py
```

Health check:
```text
/healthz
```

## Scope warning
This is a Small Bet V0, not an accounting approval system. It only parses text-based PDFs and deliberately returns `UNABLE TO VERIFY` for unreadable/scanned evidence. Do not market `Gate: CLEAR` as an approval or payment guarantee.
