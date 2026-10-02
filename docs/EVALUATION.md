# Evaluation evidence and limits

## Retrieval benchmark

The committed metric tables cover eight English queries and 288 judged
query–notice pairs. `evaluation/retrieval/queries.json` identifies dataset run
`20260925T005716341048Z`. `qrels.tsv` contains graded relevance labels (0–3).
The committed candidate pools and labels are inspectable; there is no evidence
of independent multi-rater agreement or a held-out test set.

Reproduce the README's macro means without model, database or network calls:

```bash
uv run --frozen python scripts/summarize_retrieval.py
```

- P@10, recall@10 and MRR@10 treat grade >= 2 as relevant.
- Recall is relative to the judged relevant pool, not all relevant TED notices.
- nDCG uses graded gains `2^grade - 1`; grade 1 can contribute even when binary
  precision is zero. Unjudged documents contribute zero.
- Each query has equal weight in the reported macro average.
- Hybrid weights/settings were explored on this small set. Treat the result as a
  development benchmark, not an unbiased estimate on unseen queries or languages.
- The experimental cross-encoder averages 666 ms additional reranking time in
  the committed table; it lowers macro MRR despite improving mean nDCG. Hardware,
  repetition and uncertainty are not captured sufficiently for a latency SLA.

The reported table is calculated from the committed historical evaluation files.
It does not represent a new retrieval run or a held-out evaluation of the current
database contents. For exact reproduction, use the committed query, judgment and
metric files together. Live evaluation scripts can overwrite tracked metric files,
so a separate checkout is recommended when reproducing historical results.

## RAG evaluation

`make evaluate` replays 14 hand-authored responses through the answer validator.
Passing means expected acceptance/rejection and evidence selection behave as
specified. It is not an LLM quality or hallucination-rate measurement.

`make evaluate-local` calls the configured local Ollama model on six questions
and three synthetic fixed evidence records. It checks selection/format and some
forbidden phrases. It bypasses retrieval and still requires manual factual review.
Local Ollama evaluation is separate from the deterministic answer-contract replay.
Because generated responses can vary by model version and runtime settings, local
LLM results should be reviewed manually rather than treated as a fixed benchmark.

Citation presence and exact ID matching cannot prove entailment, protect every
claim from prompt injection, or determine procurement eligibility. The prompt
and fixed insufficiency message reduce specific failure modes without eliminating
these limitations. The character context budget is not a precise token budget.

## Verification

The deterministic project checks are designed to run without TED access, a live
PostgreSQL database, Ollama or an external API key.

The current GitHub Actions workflow has been successfully executed on the public
repository. It verifies:

- Ruff static checks
- mypy across 85 source files
- 215 pytest tests
- 14/14 answer-contract replay cases
- Python source and wheel packaging
- packaged browser assets
- API Docker image build
- API import and static asset checks inside the image

These checks provide evidence for code quality and deterministic application
behavior, but they do not replace live database, retrieval or language-model
evaluation.

The unit suite uses fixtures for several database, client and encoder components.
It therefore does not establish distributed concurrency behavior or guarantee
real-world retrieval quality. Live pipeline and database checks are documented in
`docs/OPERATIONS.md`.
