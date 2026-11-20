# Learning companion landscape (as of 2026-11-11)

Method: WebSearch + WebFetch. Confidence: official = vendor/spec/repo page read; secondary = blog/review/aggregator; UNVERIFIED = single weak source or not confirmed. Many search hits were SEO blogs; prices drift, recheck before buying.

## 1. AI tutors / learning companions

| item | finding | source | confidence |
|---|---|---|---|
| NotebookLM | Google, closed, cloud. Grounded in uploaded sources. Flashcards + quizzes (topic/difficulty, "explain" with citations), "Learning Guide" Socratic chat, reports, audio. Launched 2025-09-08. No learner model across sessions found. Firefox/VS Code/iOS clients: not stated in post. Cost: not in post. Reuse: nothing (no API/learner state); gap: no concept-level model, no IDE. | https://blog.google/technology/google-labs/notebooklm-student-features/ | official |
| NotebookLM 2026 changes | No reliable 2026 feature detail found. | (searches) | UNVERIFIED |
| Claude / ChatGPT / Gemini study modes | All three do guided questioning. Claude "Learning" mode (Aug 2025), ChatGPT Study Mode (Jul 2025), Gemini Guided Learning (Aug 2025). ChatGPT Study Mode vanished briefly Apr 2026 then returned. Chat-only, no persistent concept model. Claude mode usable in Claude Projects (per one review). | https://glasp.ai/articles/ai-study-modes-compared ; https://www.tomsguide.com/ai/claudes-new-learning-modes-take-on-chatgpts-study-mode-heres-what-they-do | secondary |
| Claude Code output styles "Explanatory" and "Learning" | Official. Learning style: Insight blocks + leaves `TODO(human)` spots, stops, waits for the user to write code, then comments. Works in terminal, VS Code extension (menu needs v2.1.257+), custom styles are Markdown files in `.claude/output-styles`. Instruction-only, not enforced; hooks enforce. Proprietary client, paid Claude plan or API. Reuse as is for "write it yourself" coaching in code. | https://code.claude.com/docs/en/output-styles | official |
| Khanmigo | Khan Academy AI tutor, Socratic. About $4/mo or $44/yr individual (secondary). K-12 content, not DevOps. No reuse. | https://toolradar.com/tools/khanmigo/pricing ; https://skillscouter.com/khan-academy-review/ | secondary |
| Duolingo Max / Quizlet AI / RemNote AI | Not covered by results; no verified facts. RemNote listed as FSRS user (below). | https://github.com/open-spaced-repetition/awesome-fsrs | UNVERIFIED (Duolingo, Quizlet); RemNote FSRS = official list |
| Anki (+FSRS) | Open source desktop (AnkiMobile iOS paid, about $24.99 one-time, 5 devices same Apple ID; AnkiWeb sync free; AnkiDroid free). FSRS opt-in scheduler. Built-in self-host sync server since 2.1.57. Add-ons: Anki-GPT (beta, explanations beside cards), others. Reuse as component: scheduler, mobile apps, sync. Gap: no concept graph, no "read/code" signals. | https://docs.ankiweb.net/manual/sync-server.md ; https://docs.ankiweb.net/faqs/why-does-ankimobile-cost-more-than-a-typical-mobile-app ; https://forums.ankiweb.net/t/anki-gpt-explanations-and-follow-up-questions-beside-your-cards/71364.md | official (sync, price FAQ); secondary (price $24.99, add-ons) |
| OpenTutor (zijinz456) | MIT. Self-hosted, local-first. Ingests PDF/DOCX/PPTX (+Canvas). AI tutor with citations, quizzes (7 types), flashcards with FSRS 4.5, `learning_science` module with BKT, difficulty, cognitive load; knowledge graph experimental. Next.js + FastAPI + SQLite, defaults to Ollama, 10+ LLM providers. Single-user public beta, 174 stars, no mobile app, no YouTube/web listed. Reuse as reference/component (BKT+FSRS wiring). | https://github.com/zijinz456/OpenTutor | official (README) |
| DeepTutor (HKUDS) | Apache-2.0 per a third-party review; agentic tutor with memory; many LLM providers incl. Ollama. Not read directly. | https://themenonlab.blog/blog/deeptutor-agent-native-personalized-ai-tutoring | secondary |
| SkillClimb (danallison) | Self-hosted; per-skill-node SM-2 variant, Anthropic/OpenAI/Ollama tutor, MCP server, confidence calibration. Licence not verified. Closest to "learner model as MCP server". | https://1clonegithubbyxjn.1934672944.workers.dev/danallison/skillclimb (mirror) | secondary, licence UNVERIFIED |
| Obsidian FSRS plugins | "Spaced Repetition AI" (MIT; OpenAI cards + FSRS), True Recall, others. | https://community.obsidian.md/plugins/spaced-repetition-ai | secondary |
| Boot.dev | Paid course site; AI tutor "Boots" (Socratic, Claude Sonnet 4.5 per update note). Go course strong; has Kubernetes course. Price conflicts: $59/mo vs $33/mo, $399/yr. Closed. Web only. Reuse: as content, not tech. | https://tooldirectory.ai/tools/boot-dev ; https://dev.to/royce_fabbd83cb268312e928/bootdev-review-2026-backend-developer-path-pricing-verdict-hk8 | secondary |

## 2. Browser reading assistants (Firefox status explicit)

| item | finding | source | confidence |
|---|---|---|---|
| Firefox built-in AI sidebar | Launcher for third-party chatbots (ChatGPT, Claude, Gemini, Copilot, others). Mozilla supplies no model. Page-context features exist, but no API for your own learner logic. On-device models exist only for small features (tab grouping, alt text). Gap: not extensible. | https://support.mozilla.org/en-US/kb/ai-chatbot ; https://support.mozilla.org/en-US/kb/on-device-models | official |
| Firefox `sidebar_action` (WebExtensions) | Firefox-only manifest key. Extension sidebar = HTML page, lives while user browses (popup does not), per-window instance, can message content scripts and native host. Chrome uses different `side_panel` API (from general knowledge, MDN page silent). Own side panel is feasible. | https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/user_interface/Sidebars | official |
| Firefox on phone | No extension support (Apple restriction, not on roadmap). Safari web extensions are the iOS route (not verified in this run). | https://support.mozilla.org/questions/1201364 | secondary (forum) |
| Readwise Reader + Readwise Highlighter | Firefox add-on exists (v0.17.0, saves to Reader, highlights open web). Requires paid account: about $9.99/mo yearly or $12.99/mo; Ghostreader AI (summaries, definitions, Q&A); Daily Review spaced repetition of highlights. Closed, SaaS. iOS app: yes (not verified here). Reuse: strong if buying instead of building; gap: no learner model, no IDE. | https://addons.mozilla.org/firefox/addon/readwise-highlighter/ ; https://www.activepieces.com/blog/readwise-pricing-plans-and-costs-2026-guide | official (add-on); secondary (price) |
| YA Readwise Highlighter | Third-party Firefox add-on, highlight without button click. | https://addons.mozilla.org/it/firefox/addon/ya-readwise-highlighter/ | secondary |
| Hypothesis | Open source, BSD-2-Clause. Official extension: Chrome yes, Firefox "In development" in README (may be stale). Unofficial Firefox port by diegodlh on AMO (BSD-2). Annotations on any page, API-backed, self-hostable server. Reuse as component for highlights + storage; gap: no AI, no learner model. | https://github.com/hypothesis/browser-extension ; https://addons.mozilla.org/addon/unofficial-hypothesis/ | official / secondary |
| Sider/Monica-style panels | Not researched. | n/a | UNVERIFIED |
| Khoj | AGPL-3.0, self-hostable, clients: browser, Obsidian, Emacs, desktop, phone, WhatsApp. Any local or cloud LLM. Hosted Khoj Cloud shut Apr 2026 (secondary), project still active. Reuse as component for RAG over notes; gap: no learner model, no page highlighting. | https://github.com/khoj-ai/khoj ; https://dev.to/jovan_chan_9500711396d4e6/khoj-review-2026-your-self-hosted-ai-second-brain-28mi | official (licence); secondary (shutdown) |

## 3. IDE learning aids / code tutors

| item | finding | source | confidence |
|---|---|---|---|
| Claude Code Learning style | See section 1. The only found tool that stops and hands the user a coding task in an agent. Not tied to a learner model; not driven by missing knowledge. | https://code.claude.com/docs/en/output-styles | official |
| GitHub Copilot | No dedicated learn mode found. Official docs: put a tutor prompt in `.github/copilot-instructions.md` and disable inline suggestions. VS Code Ask mode = explain only. | https://docs.github.com/en/get-started/learning-to-code/setting-up-copilot-for-learning-to-code | official |
| Continue (Apache-2.0) | Was the open VS Code/JetBrains assistant. Acquired by Cursor Jun 2026; v2.0.0 final VS Code release 2026-06-19; repo read-only; export deadline 2026-07-15 (secondary). continue.dev homepage confirms acquisition. Code stays Apache-2.0 (fork possible). Do not depend on it. | https://continue.dev/ ; https://thenewstack.io/cursor-acquires-continue-coding/ | official (homepage), secondary (details) |
| Cursor learn mode | Not found. | n/a | UNVERIFIED |
| Boot.dev | See section 1 (web only, no IDE integration). | see above | secondary |
| Exercism | Free, open, has Go track (34 concepts, 140 exercises) with analysers and mentoring. No Kubernetes/Terraform exercises found. No 2026 AI-mentoring change found. | https://www.Exercism.io/tracks/go | secondary |
| IDE that interrupts/coaches from a learner model | None found. This is a gap. | (searches) | not found |

## 4. Open-source building blocks

| item | finding | source | confidence |
|---|---|---|---|
| FSRS libs | open-spaced-repetition org: py-fsrs (scheduler v6+optimizer), ts-fsrs (v3-v7), fsrs-rs, fsrs-browser, go-fsrs, swift-fsrs. No C# lib listed. Licences not shown on list page; check each repo (likely MIT, UNVERIFIED). | https://github.com/open-spaced-repetition/awesome-fsrs | official (list) |
| pyBKT | Python Bayesian Knowledge Tracing library, MIT (per paper), EM-fitted from response logs. Needs per-skill response logs, small data is weak. | https://arxiv.org/abs/2105.00385 | official (paper) |
| Other KT | pykt-toolkit (deep KT), OATutor (BKT, React/Firebase): named only by a search summary, not checked. | https://github.com/zijinz456/OpenTutor (BKT in use) | UNVERIFIED |
| AnythingLLM | MIT core (self-hosted terms, Mar 2026); desktop app may have own terms. Local RAG, workspaces, agents. A browser extension exists per memory, not verified. | https://docs.openwebui.com/alternatives/anythingllm/ | secondary |
| Open WebUI | Licence conflict: custom "Open WebUI License" with branding clause since v0.6.6 (several sources) vs MIT (its own comparison doc). Check LICENSE file. | https://wz-it.com/en/blog/open-webui-vs-anythingllm-comparison/ | secondary, disputed |
| Obsidian plugins | Smart Connections (local embeddings, free, Pro optional), Copilot for Obsidian (BYOK free, Plus $14.99/mo), Local GPT, many others. Mobile support disputed (desktop-only embeddings; mobile cannot reach localhost Ollama without a private VPN/LAN). | https://www.promptquorum.com/power-local-llm/local-llm-with-obsidian-2026 | secondary |
| MCP memory server (official reference) | `@modelcontextprotocol/server-memory`, local JSONL knowledge graph (entities/relations/observations), `npx -y`. Version/date sources disagree. Simple; a learner model needs richer schema (mastery, due dates). Alternatives named: Graphiti, mem0, Letta (not checked). | https://dev.to/grove_chatforest/the-memory-mcp-server-a-knowledge-graph-that-needs-a-better-brain-4o4b | secondary |
| llama.cpp | MIT. CPU (AVX/AVX2/AVX512, ARM NEON), Metal on Apple silicon, CUDA/Vulkan; 1.5-8 bit quantisation; `llama-server` OpenAI-compatible API. Fits CPU-only and Apple silicon. | https://github.com/ggml-org/llama.cpp | official |
| Ollama | Wraps llama.cpp; Apple-silicon backend moved to MLX (preview in 0.19, 2026-03-30 per Ollama blog); MLX preview reportedly wants >32 GB unified memory (one guide). Easy local API. | https://registry.ollama.ai/blog/mlx | official (blog); secondary (RAM claim) |
| MLX / mlx_lm | Apple-silicon only; fits Mac, not CPU-only Linux. Not fetched. | https://thenewstack.io/ollama-taps-apples-mlx/ | secondary |
| Small models | Qwen3-0.6B/4B, Gemma 3/4 small named in guides; speed table has unclear hardware. Gemma 4 E2B/E4B had reported 4-bit load errors on MLX. Pick by testing. | https://insiderllm.com/guides/best-local-llms-mac-2026/ | secondary |
| In-browser LLM | WebLLM (WebGPU only), transformers.js 4.x (WebGPU, WASM fallback). iOS Safari: WebGPU claimed in iOS 26, but a June 2026 test on one phone saw page reloads during generation. Too fragile for phone. | https://pinggy.io/blog/run_llm_in_browser_webgpu/ | secondary, single-device test |
| Apple Foundation Models | About 3B on-device model, Swift API, free, offline, iOS/tablet OS/macOS 26, needs Apple Intelligence device. Native app only (not PWA). WWDC 2026 added server routing (cost unclear). | https://www.macrumors.com/2025/06/09/foundation-models-framework/ ; https://dev.to/jovan_chan_9500711396d4e6/apple-foundation-models-for-developers-in-2026-on-device-swift-ai-xcode-263-agentic-coding-and-1gpa | secondary |

## 5. Ingestion

| item | finding | source | confidence |
|---|---|---|---|
| YouTube transcripts | youtube-transcript-api: MIT, no API key, uses undocumented endpoint (may break). YouTube blocks most cloud-provider IPs; fix = rotating residential proxy (Webshare class). Works from a home/laptop IP. yt-dlp subtitle download is the common fallback (cookies from browser can help). Official Data API only gives captions for own videos. Run ingestion on the owner's machine, not a VPS. | https://github.com/jdepoix/youtube-transcript-api ; https://github.com/jdepoix/youtube-transcript-api/issues/592 | official (README); secondary (yt-dlp, Data API) |
| Article text | Mozilla Readability (JS, runs inside the extension on the live DOM, after JS render) and trafilatura (Python, no JS execution). Only one small vendor benchmark (Thunderbit): trafilatura leaks less boilerplate, Readability misses fewer content units. Defuddle: no accuracy data. Extension DOM access beats server fetch for paywalled/JS pages. | https://thunderbit.com/zh-Hant/blog/trafilatura | secondary, thin |
| PDF text | Docling: MIT code, permissive default weights. Marker: weights licence restricted above $5M revenue (secondary). MinerU: licence conflicting (AGPL vs custom). PyMuPDF4LLM: AGPL-3.0, fast, weaker layout. Textbooks with code/tables: Docling or Marker for personal use. | https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026 | secondary |
| Course pages | Same as articles (Readability in extension). Login-gated course sites need the extension route. | n/a | reasoning, not sourced |

## Not found
- Any tool combining concept-level learner model + browser reading + IDE nudging.
- Cursor "learn mode"; Duolingo Max, Quizlet, RemNote AI facts; Sider/Monica Firefox status.
- Licences of py-fsrs/ts-fsrs (not on list page), SkillClimb, DeepTutor (direct), Smart Connections, Copilot-for-Obsidian.
- Official Hypothesis Firefox extension release status (README says "in development").
- 2026 NotebookLM changes; Firefox iOS extension plans; official Open WebUI licence resolution.
- A C# FSRS library (none listed; ts-fsrs or py-fsrs fit if stack is TS/Python).

## Verdicts

Reuse as is:
- Anki + FSRS + AnkiMobile + self-hosted sync for flashcard review on phone/desktop.
- Claude Code Learning/Explanatory output styles for "write it yourself" coaching in VS Code.
- llama.cpp (`llama-server`) as the local cheap-model runtime; Ollama as easy wrapper on desktop.
- NotebookLM or Readwise Reader as stopgaps for ingestion + Q&A while building.

Reuse as component:
- ts-fsrs / py-fsrs (scheduling), pyBKT or OpenTutor's BKT code (mastery per concept).
- Mozilla Readability in the extension; youtube-transcript-api / yt-dlp; Docling for PDFs.
- Firefox `sidebar_action` API for the panel; Hypothesis (or a W3C-annotation-like local store) for highlights.
- MCP memory server pattern or SkillClimb as shape for exposing the learner model to VS Code agents.
- OpenTutor / Khoj as reading references (do not adopt wholesale: beta single-user, AGPL).

Build ourselves:
- The learner model itself: concept graph (domain topics), mastery state, evidence from quizzes + reading + code.
- "Is this known" tagger prompt + cheap-model router.
- VS Code nudge/stop logic tied to the learner model and project index.
- Page overlay: new-vs-known marking.
- Thin phone PWA (review queue, quiz, chat) over the same backend.

## Three biggest feasibility risks
1. No Firefox on phone: extensions do not exist there, so "Firefox panel on phone" is impossible. Safari web extension (native wrapper) or PWA/share-sheet capture is the only iOS path,.
2. Learner-model quality: inferring "known" from reading/coding is noisy. BKT/FSRS need explicit quiz evidence; a small local model's "is this known" judgement can mislead, and false "you are ready/not ready" nudges in the IDE will annoy quickly. No prior art to copy.
3. Fragile ingestion and on-device inference: YouTube blocks cloud IPs and the endpoint is undocumented; iOS PWA storage is best-effort and WebGPU LLMs crashed on a test phone, so the "local small model" must live on the server and be reached over a tunnel (LAN or VPN), which breaks "offline on phone".

## Recommended minimal architecture (10 lines)
1. One self-hosted server (Python or Go) with SQLite: documents, chunks, concepts, mastery, review events.
2. Ingest: Firefox extension sends DOM-extracted text (Readability); server pulls YouTube via youtube-transcript-api/yt-dlp from the home or residential IP; PDFs via Docling.
3. Concept layer: cheap local model (llama.cpp `llama-server`, small Qwen/Gemma) tags chunks to a fixed concept list and judges "known?".
4. Learner model: per-concept state, FSRS (ts-fsrs/py-fsrs) for recall plus a simple BKT update from quiz and code evidence.
5. Big cloud model for explanations/quiz generation via one OpenAI-compatible router, context = retrieved chunks + learner state.
6. Firefox extension with `sidebar_action`: summary, highlight blocks (new vs known colour), Q&A.
7. VS Code extension (or MCP server + Claude Code Learning style): sends project index/symbols, queries the server for missing concepts, nudges or asks for a TODO(human).
8. Expose the learner model as an MCP server so any agent (Claude Code, Copilot) can read it.
9. phone: PWA from the same server (installed to Home Screen) for review/quiz/chat, reached over a private VPN; Anki export/sync as the offline fallback for cards.
10. Defer: native iOS/tablet app, on-device Apple Foundation Models, multi-user, voice.
