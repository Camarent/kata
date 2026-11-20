# Benchmark results (summary)

Relative findings from the model-selection suite ([`SUITE.md`](SUITE.md)). Absolute timings
are omitted because they depend on one machine; the figures below are ratios, accuracy scores
and qualitative conclusions that should hold on comparable hardware. Setup: a single consumer
GPU shared with other workloads, quantized (4-bit class) GGUF models, the llama.cpp server.
Ollama (which wraps llama.cpp) measured the same speed, so the engine is chosen by
convenience.

## Findings by task

| Task | Result |
|---|---|
| Page scan and topic tagging | A small (about 4B-class) model kept resident gave the best tagging: label accuracy 0.81 against 0.62 for the next small model; lesson check with retrieval 0.69 against 0.22; about 0.4 s per block. |
| New/known label | Every candidate picked the topic of clear blocks correctly (about 100 percent). Only the larger (about 12B-class) model followed a profile rule reliably (0.96 to 0.99). The label is therefore computed in code from the topic and the profile; models are judged only on topic and concept extraction. |
| Explanation and summary on demand | The larger model, loaded on demand and unloaded when idle, gave the best summaries and non-English quality at a few seconds to a few tens of seconds per summary. A 14B reasoning-style model was rejected: higher memory use, shallow summaries, and it answered "new" almost always. |
| Coexistence | The small resident model plus the larger on-demand model fit together at 4k, 8k and 17k context; 8k for both keeps a safe margin. Loading the larger model with the small one resident took a few seconds when files were in the OS page cache. When both generate at once each runs at roughly a quarter to a third of single-model speed, so a background scan must yield to a foreground request. |
| Parallel slots | Extra slots help only 20 to 30 percent (most at 2); use at most 2. |
| Batch work | A large mixture-of-experts model with expert layers in system RAM can handle whole decks and project-wide analysis when time is not a target. It needs most of the GPU or a reserved slice of VRAM beside the small model, and it must wait while the larger on-demand model is loaded. |
| Quality reference | A 27B-class model with partial offload was far slower (tens of seconds per summary) and is useful only as a quality reference. |
| Retrieval | A small English embedding model combined with BM25 keyword search scored an MRR of 0.68 against 0.67 for BM25 alone (noise about 0.03). Non-English queries scored lower (about 0.44) for every retriever; revisit with real data and a multilingual model. |
| Lesson check against a knowledge base | Retrieve the top entries instead of passing the whole base: the small model needs about 50 entries; the larger model is flat from 10 to 25. |
| Code and agent hints | Real-time hints in the terminal and editor use the small model: the Docker and C++ review tasks were saturated for every model, so speed decides (first token about 0.2 s). Architecture questions across many files score best on the larger model (1.00 against 0.77 to 0.87 for small models). |

## Reliability notes

- Automatic "invented command" flags were regex false positives; a manual read found no
  invented commands or facts in any model.
- Repeated runs at fixed seeds were identical for several engines; spread is reported as a
  range, and a change counts as a regression only when it exceeds the baseline noise.

## Open validation

Tool-call validity of the small model if hints use tools; a 10-minute sustained run for GPU
throttling; a first load of the larger model from disk; an end-to-end run against the
responsiveness targets; and real new/known labels from learners.
