# ComplianceRadar

Monitoring of Uzbek banks' public websites for possible gaps against CBU Regulation No. 3030
and the Law "On the State Language". Findings are only "possible gaps" with evidence; a CBU
analyst makes the decision.

> This README will be completed from facts in Stage I. The full task is in `TASK.md`.

## Run (dev)

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env
.venv/bin/pytest
.venv/bin/uvicorn backend.api.main:app --reload     # http://localhost:8000/health
cd frontend && npm install && npm run dev            # http://localhost:5173
```
