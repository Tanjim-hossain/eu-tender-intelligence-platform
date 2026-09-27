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

This delivery aggregates the existing TSVs; it does not rerun retrieval, relabel
candidates or retune ranking. The older benchmark is not a measurement of the
current 5,819-row handoff corpus. Live evaluation scripts can overwrite tracked
metric files; use a separate checkout and the matching corpus for reproduction.

## RAG evaluation

`make evaluate` replays 14 hand-authored responses through the answer validator.
Passing means expected acceptance/rejection and evidence selection behave as
specified. It is not an LLM quality or hallucination-rate measurement.

`make evaluate-local` calls the configured local Ollama model on six questions
and three synthetic fixed evidence records. It checks selection/format and some
forbidden phrases. It bypasses retrieval and still requires manual factual review.
The previous user-reported Qwen 6/6 result is historical; a raw live output report
is not supplied in this handoff and was not reproduced here.

Citation presence and exact ID matching cannot prove entailment, protect every
claim from prompt injection, or determine procurement eligibility. The prompt
and fixed insufficiency message reduce specific failure modes without eliminating
these limitations. The character context budget is not a precise token budget.

## Verification provenance

| Evidence | Source | Interpretation |
| --- | --- | --- |
| 208 baseline tests; 14/14 contract replay | Re-executed from supplied source in this environment | Deterministic baseline |
| Final quality and packaging checks | `WORK_UPDATE.md` and `docs/verification.txt` | Executed delivery checks |
| 5,819 Silver and embedding rows; zero missing/orphans | Supplied `TenderGraph-WORK-HANDOFF.md` | Prior Mac observation; not independently queried here |
| Scheduled launchd exit 0 and fresh status | Supplied handoff | Prior machine-level verification |
| Desktop/mobile screenshots and browser smoke | Existing committed artifacts / prior delivery | Synthetic API fixtures, not current live data |
| Docker build and hosted GitHub Actions | Pending | Workflow supplied; no success claim |

The unit suite injects database/client/encoder fixtures. It does not establish
real PostgreSQL transaction semantics or concurrent refresh correctness. The new
recovery regression exercises partial completion and repeat repair using simulated
durable work. Recheck the read-only SQL in the operations runbook after applying
the update on the Mac.
