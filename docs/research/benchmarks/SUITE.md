# Model-selection benchmark suite

Design of the suite that measures every candidate model on every task class and says which model should serve which role. Results are in [`RESULTS.md`](RESULTS.md). The measurement scripts are not part of the repository yet; they depend on one machine's paths and will be ported.

Goal: after any engine or model update, one command re-measures every candidate on every task class and says which model should serve which role. The always-on server must keep working during the run.

## 1. Inputs
- `candidates.yaml`: model file, engine (llama.cpp, a CPU-offload engine, Ollama), flags, role eligibility (resident / heavy / cloud).
- `tasks/`: one module per task class, each returns metrics plus pass/fail against a threshold.
- Private data stays in `a private directory outside the repository` (lessons, blocks, real labels once learners provide them). Only metrics go to the repo.
- `baseline.json`: last accepted result per (model, engine version, task). A new run is compared against it.

## 1b. Two modes
- **Interactive** (small models, resident or on demand): analysis of one lesson with sub-topics against the normalized knowledge base, realtime code hints with lookup in the base. Judged on latency (first highlights <= 2 s with the small model, one lesson scan <= 30 s), sub-topic accuracy, retrieval quality, stability. Selection: cheapest model that passes the thresholds.
- **Batch** (big model, a CPU-offload engine or similar; time is not a target): a whole slide deck, first analysis of a project's architecture, building the index. Judged on quality on long input (T8), fact coverage, endurance over hours, resumability after a failure, cold start. Selection: best quality that fits; it must run in the background without hurting the interactive roles.
- Every task below carries a `mode`; the selector runs once per mode.

## 2. Task classes (map to product scenarios)
| Id | Task | Metric | Threshold (initial) |
|---|---|---|---|
| T1 | Latency: first token at 2k/8k/15k prompt, decode tok/s | seconds, tok/s | first highlights <= 2 s (resident small model), scan <= 30 s |
| T2 | New/known tagging, profile as text, 4 entry styles | label acc., style spread | acc >= 0.9, spread <= 0.1 |
| T3 | Lesson summary: key facts, Q&A, no invented commands, language kept | facts of 12, Q&A x/6 | facts >= 9, Q&A 6/6 |
| T4 | Structured output: JSON validity under schema | valid / total | 100% |
| T5 | Concurrency: resident model keeps latency while heavy model generates | latency ratio | <= 1.5x |
| T6 | Code/agent decode (`kata term`, VS Code): decode tok/s, tool-call format | tok/s, valid calls | no regression |
| T7 | Retrieval: question over notes, right source found | recall@3 | tbd with real data |
| T8 | Long document (30k+ tokens) fact retention | facts | tbd |
| T9 | Robustness: same prompt x N, temperature 0; stability across runs | same-answer rate | >= 0.9 |
| T11 | Combinations: several small models loaded at once (one per role), total VRAM/RAM, latency of the resident role under background load | GB, latency ratio | fits budget, <= 1.5x |
| T10 | Resources: VRAM, RAM, startup time cold/warm, swap-in time | GB, s | fits the reserve |

## 3. Running with the server up
- The test never touches the production server. Candidates run in their own containers on separate ports with `--name kata-bench-*`, their own data directory, model dirs read-only.
- Before a run: read the resident server's state (model, VRAM). Compute the free VRAM/RAM budget; skip candidates that do not fit and say why (they can be run in a maintenance window with `--exclusive`).
- Two modes: `--coexist` (resident server stays loaded, tests run in the left-over budget, measures the interference too, answering "does it still work together") and `--exclusive` (server stopped, clean numbers).
- Always clean up: containers removed on exit and on Ctrl-C, GPU memory checked back to the pre-run level.

## 4. Switching models by task
- Router config `routing.yaml`: role -> model, filled from the results: `resident` (always loaded, fast), `scan` (accurate tagging), `heavy` (summaries, long docs), `cloud` (class H).
- Selection rule: for each role, among candidates that pass all hard thresholds, pick the cheapest in latency/VRAM; ties -> higher quality. A model that fails a hard threshold is rejected with the failing task named.
- The selector picks a combination of models that fits the budget (VRAM and RAM minus the heavy engine's reserve), not the best model per role in isolation. Candidates declare where they run (GPU, CPU, partial offload). Several models may be resident at once; they share GPU compute, so background work must yield to the resident role (priority queue or pauses between blocks).
- Swap cost (T10) is part of the decision: a heavy model that needs 90 s to load is only allowed for on-demand roles.

## 5. Reliability of the measurement
- Fixed seeds and temperature where the engine allows; 3+ runs per cell; report mean and spread, not one number.
- Regression test: flag a change only if it exceeds the noise measured on the baseline (e.g. 2x its spread).
- A real labelled set from a learner replaces the synthetic profile; keep the synthetic one as a smoke test.
- Public output: `RESULTS.md` row per run (engine version, model, date, metrics). No lesson text, no profile.

## 6. Build order
0. Sub-topic test (interactive): reference at concept level inside the Git and Kubernetes lessons, profile written at that level, retrieval against the normalized base (T7). Replaces the 15-topic taxonomy, which is too easy because a lesson is one topic.
0b. Batch tests: slide deck and project-architecture analysis on a CPU-offload engine vs smaller models; endurance and resume.

## 7. Scenarios (what the knowledge base is for)
Knowledge base entry = normalized concept (id, name, aliases) + state (**known / learning / new**) + evidence (source, date) + the learner's free-text note. Three states, not two: the earlier tests only had new/known.
1. **Lesson check.** Open a lesson, split into blocks, find the concepts of each block, look them up in the base, show known / learning / new per block (interactive mode).
2. **Question about commands**, e.g. "which commands clean up after tests", "how to list running Docker containers and clear their build cache". Answer from the base and the learner's own scripts first; if the base has nothing, the model must say so and answer from general knowledge, marked as such.
3. **Question about own code**, e.g. "which mandatory methods and modifiers have I not specified in this C++ class" (special members, const, noexcept, override, explicit). Needs the code in context plus a checklist from the base; answer is a diff of "required" against "present".
Test types this adds: three-state lookup accuracy, "base has no answer" (abstain) cases, answers that combine a code file with a checklist, and real learner questions (the three above are the first seeds).
