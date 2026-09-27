# Work update — 27 September 2026

## Completed milestone

Continued from `TenderGraph-Latest-20260927-010932.zip`, preserving the uploaded
relevance-selection pipeline and the existing ingestion/retrieval code.

- Added a responsive browser workspace at `/` with tender search, buyer/value/
  deadline cards, questions, supporting sources, answer JSON download, and clear
  loading, empty, and failure states. It uses the server's existing answer mode.
- Added read-only `/config`, exposing mode/model/reranking without credentials.
- Fixed the double-escaped evidence-ID regex, including case-insensitive detection
  of unselected IDs mentioned in prose.
- Added `insufficient_evidence` when the generator selects `RELEVANT: NONE`. It
  returns a fixed message with no sources, instead of passing unverified prose.
- Kept strict selection/citation matching and rejection of unknown/duplicate IDs.
- Added sanitized database-unavailable handling for `/search`.
- Fixed the local audit script's all-requests-failed summary crash.
- Added 14 offline answer-contract cases, six synthetic local-model cases,
  a report-writing evaluation runner, browser checks, and Makefile shortcuts.
- Added `START_HERE.md` and a credential-free `.env.example`. Existing `.env`,
  local data, model installation, Docker volume, and Git history are reused.

## Verified here

- `uv sync --frozen`: completed against the uploaded lockfile.
- `ruff check .`: passed.
- `mypy src scripts`: passed, 67 source files.
- `pytest -q`: **145 passed**.
- Offline answer-contract replay: **14/14 passed**. No model called.
- Browser smoke: passed search, cited answers, JSON download, abstention, unsafe
  text/URL rendering, 503 errors, preserved inputs, and evidence-mode labels.
- Desktop 1440px and mobile 390px screenshots inspected. Mobile has no horizontal
  overflow. Screenshots use clearly labelled synthetic notices/answers.
- Wheel build passed; all three HTML/CSS/JS assets are packaged.

The browser test runs the real static assets through FastAPI with API responses
intercepted by test fixtures. Python API and pipeline tests use injected retrieval
and evidence fixtures; Ollama HTTP behavior uses a mock transport.

## Not verified here

No live PostgreSQL retrieval, local Ollama generation, or paid OpenAI call was made
in this environment. The six-case model suite is ready to run on the Mac but has
not been scored here. Passing ID/format checks does not prove factual support or
real-world relevance. Existing retrieval evaluations are preserved, not rerun.

## Next local steps

Follow `START_HERE.md` to merge this source update and start the API. Open
http://127.0.0.1:8000 and try the existing hospital-information-system search.
Then run `make evaluate-local` with the installed Ollama model and review each
answer against its case's manual review criterion.

Scheduled refresh, production authentication, and public deployment remain future
milestones. This update completes the browser workspace and evaluation tooling;
it does not claim the whole production roadmap is complete.
