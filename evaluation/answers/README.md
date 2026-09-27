# Answer evaluation

- `contract_cases.json`: 14 hand-authored outputs. Offline validator regression
  cases, including bad IDs, unselected mentions, duplicate selections, missing
  citations, and abstention. Run `make evaluate`.
- `quality_cases.json`: six questions on three synthetic tender records. Tests
  selection, comparison, unsupported topics, missing amounts, and the distinction
  between tender deadlines and service end-of-life dates. Run `make evaluate-local`
  with your existing local Ollama settings.
- `reports/`: generated evaluation output. Offline runs write
  `contract_replay.json`; live local-model runs write `local_model.json`.
  These reports are intentionally ignored by Git because timestamps, latency,
  and model output can change between runs.
- `browser/`: screenshots from browser interaction checks, when available. All
  displayed notices and answers are synthetic fixtures, not procurement findings.

The live suite bypasses retrieval, so it does not measure ranking performance.
Expected selections are hand-authored. The evaluator checks the response contract,
selected ID set, and specified forbidden phrases; it cannot automatically establish
factual support. Read each live case's `review` criterion against its answer.
Providers have no automatic retries or paid fallback.

Browser checks use real FastAPI static assets with intercepted API responses:

```bash
npm install --no-save playwright
npx playwright install chromium
node tests/browser/ui_smoke.mjs
```

The browser test requires an existing `.venv`, Node.js 20+, and a free port 8876.
An optional `CHROMIUM_EXECUTABLE_PATH` selects an already installed browser.
It does not start the production lifespan, PostgreSQL, or Ollama.
