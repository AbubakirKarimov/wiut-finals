import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");

const API_PORT = 8001;
const WEB_PORT = 5174;
const SITE_PORT = 18765;
const PY = process.env.E2E_PYTHON || path.join(ROOT, ".venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}` },
  projects: [
    { name: "mobile-390", use: { browserName: "chromium", viewport: { width: 390, height: 844 } } },
    { name: "desktop-1280", use: { browserName: "chromium", viewport: { width: 1280, height: 800 } } },
  ],
  webServer: [
    {
      command: `${PY} -m http.server ${SITE_PORT} --bind 127.0.0.1 --directory e2e/fixture-site`,
      url: `http://127.0.0.1:${SITE_PORT}/index.html`,
      reuseExistingServer: false,
    },
    {
      command: `${PY} frontend/e2e/seed.py && ${PY} -m uvicorn backend.api.main:app --host 127.0.0.1 --port ${API_PORT} --workers 1`,
      cwd: ROOT,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      env: {
        DB_PATH: "frontend/e2e/.tmp/e2e.sqlite",
        // Isolated from the team's data/requirements.yaml; seed.py adds one test requirement.
        REQUIREMENTS_PATH: "frontend/e2e/.tmp/no-requirements.yaml",
        PRECOMPUTED_PATH: "frontend/e2e/.tmp/no-precomputed.json",
        CHECK_ALLOW_PRIVATE_URLS: "1",
        CHECK_RATE_LIMIT_PER_MINUTE: "100",
        CRAWLER_MIN_DELAY_SECONDS: "0.2",
        CRAWLER_MAX_PAGES_PER_BANK: "15",
        CRAWLER_TIME_BUDGET_SECONDS: "60",
        BROWSER_FALLBACK: "0",
        CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT}`,
        LLM_BASE_URL: "",
        LLM_API_KEY: "",
        LLM_MODEL: "",
        LLM_FALLBACK_1_BASE_URL: "",
        LLM_FALLBACK_1_API_KEY: "",
        LLM_FALLBACK_1_MODEL: "",
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      env: { VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
