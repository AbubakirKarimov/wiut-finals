# ComplianceRadar

Мониторинг публичных сайтов банков Узбекистана на возможные несоответствия Положению ЦБ №3030
и Закону «О государственном языке». Находки — только «возможное несоответствие» с
доказательством; решение принимает аналитик ЦБ.

> README будет заполнен по факту на этапе I.

## Запуск (dev)

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env
.venv/bin/pytest
.venv/bin/uvicorn backend.api.main:app --reload     # http://localhost:8000/health
cd frontend && npm install && npm run dev            # http://localhost:5173
```
