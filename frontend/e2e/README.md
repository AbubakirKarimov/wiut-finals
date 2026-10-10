# End-to-end tests

`npx playwright test` starts three servers (see `playwright.config.js`):

- `fixture-site/` on http://127.0.0.1:18765: a small, made-up Russian-only test site
  (test fixture, not a real bank),
- the API on http://127.0.0.1:8001 with a throwaway database seeded by `seed.py`
  (`CHECK_ALLOW_PRIVATE_URLS=1`, LLM disabled),
- the Vite dev server on http://127.0.0.1:5174.

Screenshots are written to `e2e/screenshots/` at 375, 768 and 1280 px; the 375 and 1280 px ones are also copied to `eval/ui_screens/`. Every page is checked for horizontal scroll, and the home page for tap targets of at least 44 px.
