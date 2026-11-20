# Design critique

Findings from an independent review of an earlier version of the architecture, kept as a record of risks and of what was cut or deferred. Finding numbers are stable references. Some findings were fixed in later revisions of [`detailed-architecture.md`](detailed-architecture.md); the list is not a current to-do list.

## 1. Verdict

The design is coherent, honest about its unknowns and well grounded in the notes, but it is sized for a small product team, and its main latency target is not supported by the benchmarks once the design's own additions (summary in parallel, concept output, per-call scanner) are counted. Milestone 0 as sliced (S0 to S3) is too large and its central output, the new/known label, is not defined for the data that exists at that point. Fix first: (1) the scan path and its target definition (F1, F2, F3), (2) the isolation mechanism details and the same-origin trainer pages (F4, F5, F6), (3) a smaller first slice with the measurements and spikes moved to the front (F8, F9).

## 2. Findings

Severity: blocker = the stated goal fails or the slice cannot be built as written; major = wrong result, security hole or large rework; minor = local fix.

### Blockers

**F1. The 30 s scan target does not survive the design's own flow.** Severity: blocker. Where: 1.4 "6 to 13 s of margin", 8.1 step 6, 9.4, 18 R1; figure 4 caption.
- Wrong: the margin is taken from tagging alone, one model on the GPU. The flow starts the class M summary in parallel with tagging. `RESULTS` (E4B plus 12B coexistence) measures the small model at about 27 tok/s while the 12B generates, against 86 to 96 alone (about 30 percent). Generation is 8 to 15 s of the 21 s lesson (`RESULTS` prompt cache table), so the overlap with a 7 to 12 s summary adds roughly 10 s or more. `SUITE` T5 sets a threshold of 1.5x for exactly this case; the measured ratio is about 3.3x.
- Also: "17 to 24 s" mixes a rejected model and one slot. For the chosen configuration (E4B, two slots) the number is 21.1 s, so the true starting margin is about 9 s, from single runs where "differences under about 25 percent are noise".
- Also: `done` is emitted after `summary.delta` and `card` (8.1 step 7), while 1.4 measures "scan start to the `done` stream event" and 8.1 says the summary "has no latency target". The two statements conflict.
- Why it matters: the headline target fails on the reference hardware in the normal case, not in an edge case.
- Fix: run the summary after tagging finishes (or on class L, 2 to 4 s per `RESULTS` T2); define the 30 s as "last `block` event" and give the summary its own event (`tags_done`, then `done`); state the target for E4B with two slots on the reference GPU only.
- Confidence: high for the contention numbers (measured); medium for the total. Settled by the R1 run with the summary running, which should be done before S2 is designed.

**F2. The tagging task in the design is not the task that was benchmarked.** Severity: blocker. Where: 8.2 steps 1 to 3, 1.4, 15 S2.
- Wrong: the benchmark prompt returns a topic (about 60 output tokens per block). The design returns "a topic id from the list and concept names". More output tokens raise generation time, which is already half the lesson time. No measurement covers topic plus concepts, and none covers a real shared topic list (the benchmark prefix was about 190 tokens).
- Also: concept names are resolved "by alias", and `RESULTS` (free-vocabulary concepts) shows that matching free concept names to entries is fragile (0.66 to 0.94 by wording, even with embeddings). Exact alias matching will resolve fewer.
- Why it matters: the latency claim and the accuracy claim for M0 both rest on a different task.
- Fix: M0 tagging returns the topic id only (benchmarked, about 100 percent on clear blocks). Concept extraction arrives with S6, behind its own measurement.
- Confidence: high. Settled by rerunning `kbench` with the product prompt and schema.

**F3. The label function is undefined for Milestone 0 and biased to "new" afterwards.** Severity: blocker. Where: 7.6, 7.5 "Grain", 15 S1 ("knowledge states at topic level").
- Wrong: 7.6 computes the label from "the block's concept references" by percentages, and "a concept with no node counts as new". In M0 there are only topic-level states and no concept taxonomy (it comes in S6), so every concept is unresolved and every block is `new`. After S6 the same rule plus fragile alias resolution (F2) still pushes labels to `new`. The 30 percent rule comes from a reference set where 82 percent of blocks were new (`RESULTS` lesson check), so it was never tested against a profile with much known material.
- Why it matters: the product's main output (which blocks are new) is wrong or constant in the first milestone; two implementers would build different rules.
- Fix: specify two rules. M0: label = state of the block's topic (the benchmarked rule). Later: concept rule over resolved concepts only; unresolved names are ignored for the ratio and shown as "unknown term", with a minimum number of resolved concepts before the concept rule overrides the topic state.
- Confidence: high on the gap; medium on the bias size. Settled by R2 (real labels).

### Major

**F4. Row-rule mechanism: three details that break it as written.** Severity: major. Where: 7.2 (rows "Row rules", "Transaction", "Cross-user operations", "Database roles"), 7.10.
- (a) "With the setting absent the policy matches no row": on a pooled connection that has used a custom setting once, the value after the transaction is an empty string, not absent; a cast to a UUID then raises an error instead of matching no row. The raw-connection test in 7.2 uses a fresh connection and will not see it. **Needs verification** (Postgres behaviour of custom settings after `SET LOCAL`).
- (b) Row security is "enabled and forced", which also binds the table administrator. Definer functions owned by `kata_owner`, data migrations ("run as database functions") and `kata_backup` ("reads everything") then see no rows unless a role has the bypass attribute or the function sets the user itself. The document gives no role that may bypass. **Needs verification** (forced row security and definer functions; dump tools refuse to run under row security without bypass).
- (c) "each request opens a transaction": stream endpoints (`/stream`, device stream) live for seconds to hours. One transaction per stream pins a connection and blocks vacuum; the notify listener (8.11) needs a dedicated session connection outside any transaction pooler.
- Why it matters: either errors in production after connection reuse, or definer functions and backups that silently return nothing, or pool exhaustion with a few open panels.
- Fix: policy uses a null-safe read of the setting; name one non-login role with bypass that owns the definer functions and one for backup; state that streams hold no transaction (short transaction per emitted batch) and that one listener connection is owned by `kata-core`. Add a test that reuses one connection for two users and one for "no user after a user".
- Confidence: medium-high. Settled by a 30-line SQL spike before S1.

**F5. Trainer pages share an origin and a cookie with the whole API.** Severity: major. Where: 6.5 "Identity", 11.2 step 7, 8.9, 17 Q26.
- Wrong: built course pages contain model-generated items made from lesson text (web content) and are served from the core's origin, where the session cookie is a full device token. Any markup or script that survives into a built page runs with the user's session: it can read the profile, mint enrolment codes (F10) or delete the account. `SameSite` and the origin check do not help against same-origin script.
- Fix: serve `/trainer/` from a separate origin (second name on the proxy) with a cookie of a narrow `trainer` scope limited to that course's progress endpoints; add a strict content security policy on both origins; treat generated item text as untrusted in the build.
- What is lost: one more name and certificate.
- Confidence: high on the exposure; medium on exploitability (depends on how the trainer tool renders item text: verify escaping in its renderer).

**F6. Shared annotations are resolved against a private overlay.** Severity: major. Where: 8.2 step 3 against 7.3 ("derived from content only") and 7.4.
- Wrong: step 3 "resolves concept names by alias (shared, then the user's overlay), stores the result in `chunk_annotation`", which is a shared table. The stored result then depends on one user's private aliases and can reference private node ids; another user reads it. Also the key includes the taxonomy version, so every admin edit of the shared tree invalidates all cached annotations and forces rescans.
- Fix: `chunk_annotation` stores the topic id from the shared list and raw concept names only. Resolution to nodes (shared, then overlay) happens per user at read time and is cached in `scan`. Key the annotation by task version and topic-list version, and re-resolve instead of re-tagging when aliases change.
- Confidence: high.

**F7. The architecture contradicts the note that is declared authoritative.** Severity: major. Where:.md` is authoritative"),, architecture 6.3, 9.3, 9.6, 17 C2.
-; architecture and.
-; architecture 9.3: `tag` falls to "cloud small".
-;.
-; architecture 7.5 and 11.4 say no scheduling library and gitleaks.
- C2 asks to "correct the sentence in; that sentence is already corrected, so C2 is stale.
- Why it matters: an implementer who follows the authoritative note builds a different model path.
- Fix: edit) and close C2.
- Confidence: high.

**F8. Milestone 0 (S0 to S3) is too large for a first slice and hides its dependencies.** Severity: major. Where: 15, 17 C12.
- S0 to S3 include: three database roles and row rules with a full isolation suite, enrolment, the egress gate with a scanner subprocess, atomic cost reservation, two cloud adapters, resumable streams, schema and type generation, journal, outbox, cache, graded-page detection. None is testable by a user until S3.
- Out of order: S2 tagging emits concepts and overlay suggestions (8.2) but the concept taxonomy and overlay are S6; `content` "depends on `jobs`" but jobs are S5; the reservation sweeper (9.7 step 5) and retention need a periodic runner that M0 does not have ("no job runner", 4.1); backups appear only in S8 although private data is stored from S3; deletion is S5 although pages are stored from S3.
- On the workstation the model endpoint is on the same machine, so M0 does not need the worker protocol at all, yet the cloud path is the only required one and it is unmeasured.
- Fix: a walking skeleton first: extension (one site, click or open) to `POST /v1/scans` to one `openai_compatible` adapter pointed at the local endpoint on loopback (descriptor flag `trusted`, no gate), topic-only tags, topic-level label, marks. Keep tokens and row rules (cheap now, costly later), add a nightly dump on day one, add delete-document. Defer to after M0: Claude adapter, reservation ledger (use a simple spend counter), stream resume, journal, graded-page logic beyond a manual "silent here" switch.
- Confidence: high on size and order; the cut list is a judgement.

**F9. Spikes and measurements that can change the design are scheduled after the design is built.** Severity: major. Where: 15 S10 (terminal spike), 18 R1, R3, R6, R8, R10.
- R1 (end-to-end latency) decides the scan flow (F1, F2) but runs after S2 and S3 exist. R3 decides the device tool's shape and language (F12). R10 (`registerStorage` contract) is only "verify first" inside S11. R8 (scanner time) decides the cloud path of M0.
- Fix: a "S-1" spike slice with four throwaway scripts: latency with the product prompt and summary contention; scanner per-call time; SSH capture; the trainer storage hook round trip. Each produces a number or a yes/no in `RESULTS`.
- Confidence: high.

**F10. Token scopes and enrolment do not match the endpoints the clients call.** Severity: major. Where: 11.2 steps 5 and 7, "Scopes", 11.3, 5.3, 8.7 step 3, 6.5 "CLI import".
- The device tool token has scope `ingest` ("events and sources, write-only, plus own messages"), but `kata precommit` calls `POST /v1/diffs/check` and `kata progress import` calls the trainer import endpoint. Both are outside `ingest`.
- "an enrolled device may request a new code": no scope is named. If `ingest` or `mcp` tokens may do it, the weakest token (a file on disk, or a token in an assistant's configuration) can mint a full device. If only `app` may, a script on the core origin still can (F5). Revoking a device does not revoke devices enrolled from it.
- The extension token sits in the extension's local storage area, which content scripts of that extension can read in at least one browser by default (**needs verification**), and it has scope `app` including `DELETE /v1/me`.
- Fix: a scope table that maps every endpoint group of 6.1 to scopes (part of the API schema, tested); new-device codes need `app` plus a fresh confirmation in a panel; destructive calls (`DELETE /v1/me`, device removal) need a second step; record "enrolled by" and offer cascade revoke.
- Confidence: high on the mismatch.

**F11. Prompt injection is answered only for tagging.** Severity: major. Where: 11.1 T4, 6.4, 8.4, 8.5 step 6, 8.9.
- T4 covers "scan and tag tasks". Not covered: (a) MCP: `kata_search` returns notes, concept entries and optionally material text to an assistant that has tools (shell, file edits). Text from a web page or a model-suggested concept name becomes an instruction to that assistant. (b) Terminal: model or template text is printed by the proxy into the user's terminal; control sequences in it can rewrite the screen or worse. (c) Explanations: retrieved web text enters the prompt together with notes and states; if the panel renders links or images, the answer can carry data out. (d) Course generation: lesson text to model to item text to a page (F5). (e) Overlay names: model-made `suggested` names later re-enter prompts as candidates.
- Fix: one rule per sink. MCP results are wrapped as quoted data with a fixed prefix, length-limited, concept names restricted to a character class; material text stays off. Terminal lines are stripped to printable characters and a length limit in the proxy. Panels render model text as plain text with no automatic link or image loading. Suggested names are validated (length, characters) before storage. Add an injection fixture page to the test set (F29).
- Confidence: high on the gaps; exploitability depends on the assistant.

**F12. The terminal tool as specified cannot be built, independent of the SSH spike.** Severity: major. Where: 5.3 "one bundled file run by Node, no runtime dependencies", 5.4 "Mechanism".
- A pseudo-terminal proxy needs a native module or an external helper; the runtime named has no built-in pseudo-terminal (**needs verification**). "No runtime dependencies" and "pseudo-terminal proxy" conflict.
- "standard shell-integration escape sequences (command text, command start, exit code)": the common standard marks carry prompt and command boundaries and the exit code; command text is an editor-specific extension (**needs verification**). The hook must emit a custom, escaped payload, and a multiplexer on the remote side drops unknown sequences unless passthrough is on.
- "SSH: injected into the remote shell at session start" does not say how: typing into the stream races with login banners, password and second-factor prompts; changing the remote command changes what the user asked SSH to do; old remote shells lack the pre-execution hook.
- Fix: decide the mechanism in the spike, with these candidates in order: wrap the system `script`-style helper or write the proxy in the worker's language (it already supervises processes); define the mark format (one private sequence with encoded command text and a per-session nonce so remote output cannot forge events); inject only after the first prompt is seen, never during authentication.
- Confidence: medium-high. Settled by the R3 spike, which should include the nonce and a forged-mark test.

**F13. Browser extension: Manifest V3 limits are not addressed.** Severity: major. Where: 5.3 (extension row), 6.1 "Streaming", 8.1, 15 S3 and S15.
- The background part is not persistent in either browser (event page in one, service worker in the other); a long `GET /v1/stream` or scan stream held there is killed when the background is suspended. A stream read by `fetch` may not keep it alive (**needs verification** per browser).
- "side panel" is a different API in each browser (sidebar action against side panel); the polyfill does not unify them (**needs verification**).
- "the scan starts on page open without a click" needs host permission for the site; in one of the two browsers host permissions under Manifest V3 are granted by the user per site and can be withdrawn (**needs verification**). Single-page course sites change lessons without a page load, so "page open" needs navigation detection.
- Distribution:. The design has a `client_too_old` path but no way to install or update the extension, the editor extension or the device tool on other users' machines.
- The Chrome build is in the last slice (S15), so these differences are found last.
- Fix: scan streams are opened from the side panel or content script context, not the background; device messages in version 1 come by piggyback and a poll while a panel is open (drop the extension's device stream); write the per-browser table (background type, panel API, permission flow, signing) in section 5.3; build both targets in CI from S3; add a distribution subsection (self-signed unlisted signing, a packaged editor extension, one install script).
- Confidence: medium (browser details need verification), high that the section is missing.

**F14. Memory budget on the worker is proven only for a headless GPU with one slot per model.** Severity: major. Where: 9.4 "At most 2 slots per model", 9.5 "margin (default 500 MiB; measured free margin is 0.95 to 1.4 GB)", 18 R9.
- `RESULTS` coexistence: free margin 1182 MiB at 8k, with "no desktop session using the GPU (13 MiB used)" and "Not tested: a second slot on either model". The design uses two class L slots, and in M0 the worker is the workstation with a desktop, a browser and an editor ("typically 300-800 MiB").
- Why it matters: with a 500 MiB check margin the class M load is refused in the common case, so summaries and explanations silently go to cloud (cost, privacy class) or to "passages only".
- Also unmeasured: any second user's smaller GPU; the targets are defined only for the reference card.
- Fix: measure E4B with two slots plus 12B at 8k under a real desktop session; if it does not fit, choose one of: one L slot while M is loaded, 12B at 4k, or summary on class L. State in 1.4 that targets hold for the reference GPU.
- Confidence: high that it is unmeasured; medium on the outcome.

**F15. Automatic scan on page open has no stated consent boundary.** Severity: major. Where: 8.1 step 1 ("the scan starts on page open without a click"), "site switch" (undefined), 9.4 P2 `scan.prefetch`.
- Wrong: step 5 stores source, document and chunks for every scanned page. Whether the site switch is an allow list or a deny list, and its default, is not stated. With a deny list every page the user opens (mail, bank, private documents) is posted, stored in a table shared by hash, and for a cloud-only user sent to a provider and charged.
- Fix: allow list only, empty by default, added per site from the panel ("always scan this site"); elsewhere scan on click; state it in section 2 as a principle. For cloud-only users make prefetch a setting, off by default.
- Confidence: high that it is unspecified.

**F16. Code and diffs: the default cloud policy is unsafe and the flag has no home.** Severity: major. Where: 11.4 step 1 ("public code ... may go to any provider"), 6.1 `POST /v1/code/check`, `/v1/diffs/check`, 9.3 (no task class for code checks),).
- Wrong: the core cannot know whether a hunk is "public code". The `local_only` project flag is said to be in configuration, but which configuration (client, core, per user) and how a repository is identified are not stated. No task class exists for `code/check`, so its chain and priority are undefined.
- Why it matters: an employer's or private repository is sent to a cloud provider by default on every save for a user without a worker.
- Fix: content class `code` defaults to worker-only; cloud needs an explicit per-repository opt-in stored per user on the core, keyed by a repository id the client derives; add task class `code_check` (class L, P2) to 9.3.
- Confidence: high.

**F17. Concept-level lesson check has neither a time nor a usable accuracy number.** Severity: major. Where: 8.3 ("about 50 for class L"), 15 S6, 18 R2.
- `RESULTS`: E4B needs the top 50 entries; at 25 entries the prompt is about 1.1k tokens and 0.35 s per block (model-decided label). At 50 the prompt roughly doubles, and prompt reading dominates time, so a 55-block lesson moves well past the F1 budget. Best mean class recall is 0.81 under an optimistic reference ("the base always contains the block's own concepts").
- Fix: treat S6's lesson check as an experiment with an exit criterion (time and class recall on real labels); keep topic-level labels as the shipped behaviour until it passes; consider running the concept pass only on blocks whose topic is `learning`.
- Confidence: medium. Settled by R2 with timing.

**F18. Restore, rollback and deletion interact badly.** Severity: major. Where: 7.8 "Backups", 7.10 ("takes a dump before it applies anything"), 12.2, 12.3 step 5, 4.3 step 8.
- A restore brings back revoked device tokens, deleted users and deleted documents. Pre-migration dumps and the old host's stopped database are outside the rotation ("a fixed number of days") and are not said to be encrypted. Rollback is "the previous image plus the dump", which discards every event clients sent after the upgrade; clients have already removed those from their outboxes.
- There is no procedure for a failure after step 7 of the relocation: if the old host leaves maintenance while some clients already write to the new one, the data splits.
- Fix: keep a small append-only file beside the backups with revocations and deletion receipts (ids only) and replay it after any restore; give pre-migration dumps the same encryption and rotation; require backward-compatible migrations so rollback is "previous image, same database" (expand and contract is already the rule in 7.10); after step 7 the old host may only be re-enabled after a reverse dump.
- Confidence: high.

**F19. Worker link: liveness and admission timing are unspecified.** Severity: major. Where: 6.3 "Presence", "Lost worker", 9.6.
- A sleeping workstation leaves a half-open connection; "two heartbeats are missed" with no interval given can be tens of seconds. In that window an interactive request is sent to a dead socket and the 2 s target is gone; the `accepted` frame has no deadline. After resume the worker must itself notice the dead socket. The reverse proxy's idle timeout and response buffering for streams are not mentioned.
- Fix: heartbeat and transport ping of a few seconds; `accepted` within a short configured time or the request moves on; the worker reconnects on resume from sleep (system event or ping failure); proxy settings for upgrade, idle timeout and unbuffered streams listed in 4.2; test with a real suspend, not only a fake worker.
- Confidence: high.

**F20. Per-call scanner subprocess on the cloud scan path.** Severity: major. Where: 11.4 step 2, 18 R8, 1.4 ("Through cloud: unmeasured").
- A lesson is about 55 cloud calls; each starts a scanner process that compiles its rule set. Even at 100 to 300 ms each this is 5 to 15 s serial, on a path with no measurement at all, and it is the only required model path of M0.
- Also inconsistent: uploaded files with a secret are "rejected at ingestion and not stored" (7.3), but page blocks posted by the extension are stored and embedded without a scan (8.1 step 5);.
- Fix: scan each chunk once at intake and cache the verdict by chunk hash and scanner rule version; at call time scan only the parts that are not chunks (question, notes, command). A chunk with a hit is stored with a `never_cloud` flag rather than rejected.
- Confidence: medium on the time (unmeasured), high on the inconsistency.

### Minor

**F21. Module dependency table contradicts the flows.** Where: 5.1 against 8.5 step 5, 11.4 step 2, 8.11; figure 3. `policy` "writes the journal entry and a message" but depends on neither `journal` nor `delivery`; `egress` "writes a journal entry" but depends only on `storage`; job handlers for `ingest.document` or `course.build` live in `content` and `trainer`, which depend on `jobs`, so the runner must call upward. Fix: add the missing edges; state that `jobs` is a registry that features register handlers with. Confidence: high.

**F22. System tables and the catalogue test conflict.** Where: 7.1, 7.2 "Tests". `device`, `device_token`, `worker`, `user_limit` carry a user id but are "System" tables without the row rule; the test "lists every table with a `user_id` column and fails" on them. Also `GET /v1/auth/devices` is a per-user read of a system table. Client-made ids: only `event` is said to be unique per (`user_id`, `id`); a global primary key on other tables lets one user's id collide with another's and leak existence through a conflict error. Fix: row rule on per-user system tables with an explicit exemption list in the test; primary keys (`user_id`, `id`) on all client-id tables; a repeated create with a different body returns `409`. Confidence: high.

**F23. Page fetcher rules are incomplete.** Where: 8.10, 11.1 T5. Not stated: resolve once and connect to the checked address (rebinding), the VPN's own address range, IPv6 local ranges, non-HTTP schemes, response type limits. The core host runs unrelated services, so loopback and the home network are real targets. Fix: an explicit deny list (loopback, private, link-local, carrier-grade and VPN ranges, IPv6 equivalents), pinned resolution, HTTP(S) only, redirect limit; a test list. Confidence: high.

**F24. Trainer progress to evidence is under-specified.** Where: 6.5 "Evidence", 8.8. Not defined: a progress reset (`resetAt`, counters go down), merged saves that contain another device's results, what the deterministic id is built from, and negative deltas. Browser storage for the trainer is keyed per course and origin, so two users on one shared browser profile see and upload each other's local copy. The merge command for two progress documents does not exist yet (6.5 "proposed"). Fix: evidence id = (course, item, `ok`, `bad` counters); a reset writes no negative evidence; the adapter namespaces the local key by user id and clears it on a session change. Confidence: medium; settle with the the trainer tool contract.

**F25. Summary input can exceed the class M context.** Where: 9.5 ("M ... at 8k context"), 8.1 step 6. A lesson of 55 blocks at up to 900 words does not fit 8k tokens; truncation or a two-stage summary is not specified, and a two-stage one changes the timing in F1. Fix: define the rule (headings plus first sentences up to a token budget, or per-section summaries from class L). Confidence: high.

**F26. Stored terminal commands cannot be seen or deleted one by one.** Where: 7.8 "One event or journal entry", 6.1 (no `GET` or `DELETE` for events). The deletion table promises it; the API has no endpoint. After 90 days `evidence` rows point at deleted events ("source event"). Fix: `GET /v1/events` (own, paged) and `DELETE /v1/events/{id}`; make the evidence source reference nullable by design. Confidence: high.

**F27. Clock and order rules conflict with "pure function of the evidence set".** Where: 6.2 "Clock", "Order", 7.5 "Rule". "An assertion ... holds until a configured number of contrary trainer or test results" depends on order, and order across devices is by client `occurred_at`. "Clamps to the receive time" is not defined for a clock that is behind (a real offline event and a wrong clock look the same). `seq` after a reinstall is not defined. Fix: clamp to [receive time minus queue age limit, receive time]; send the client's "now" with each batch so the core can correct skew; define the function over the evidence ordered by corrected time. Confidence: medium.

**F28. Batch mode on the first core host.** Where: 9.5 `batch_coexist`, 12.5, 15 S13, benchmark results. The batch engine holds most of the workstation's RAM; while the workstation is also the core host, the kata ceiling of about 14 GB does not fit. In `batch_coexist` the small model is "about 3.5 times slower while both generate", so a scan misses 30 s; the design only covers an arriving class M request. Fix: S13 depends on S8 (core moved); in `batch_coexist` an interactive scan pauses the batch job between steps or is declared out of target. Confidence: high (measured).

**F29. Test plan holes.** Where: 13.
- No test for: prompt-injected pages and MCP results (F11); script in generated course items (F5); the fetcher deny list (F23); connection reuse under row rules and definer functions (F4); restore with revocations (F18); real suspend and resume of a worker (F19); a shared browser profile (F24).
- Latency: one run per point in `RESULTS`; the plan has no cloud run, no VPN run, no run with the summary active, no first load of class M from disk, no desktop-session memory run.
- The product's main quality number (label accuracy on real labels) has no administrator step, data format or pass threshold in 13; `SUITE` T2 threshold (0.9) applies to a model-decides task the design no longer uses.
- Browser automation for an extension side panel in the first target browser is listed as "CONFIRM which" in; the end-to-end layer depends on it.
- Fix: add the rows; three runs per latency cell; a labelled-set task with a threshold on mean class recall. Confidence: high.

**F30. Operating burden on one person is larger than section 12 shows.** Where: 12, 4.2. Not counted: signing and updating three client kinds on each small group machine (F13); keeping other users' workers updated and within one protocol version; hand-maintained provider price tables with peak hours (6.6); curating model-suggested taxonomy nodes; a scheduled restore drill; a metrics server to scrape the endpoint; the backup key; scanner, trainer binary and embedding model pinned in the image. Sharing one Postgres instance with unrelated services ("own database and roles") ties kata to their upgrade cycle and gives their superuser access. Fix: a dedicated Postgres container for kata; one `kata doctor` command instead of a metrics stack in version 1; prices as one flat table without peak logic until a provider needs it. Confidence: medium.

**F31. Keyword search column.** Where: 7.9. "a generated text-search column ... using the chunk's language configuration, with identifier splitting": a generated column needs an immutable expression; choosing the configuration from another column and custom splitting usually need a wrapper declared immutable (**needs verification**). Mixed-language text (non-English prose, English terms) fits neither configuration; `RESULTS` shows non-English queries weak for every retriever. Fix: decide inside the Q7 comparison; consider a `simple` configuration plus splitting as the baseline. Confidence: medium.

**F32. Commit hooks: edge cases.** Where: 8.7. A stale marker is never removed (pass, abort the commit, then commit the same tree with `--no-verify`: not detected); commits created by rebase, merge or cherry-pick may run post-commit without pre-commit and log a false bypass (**needs verification** per git operation); existing hook managers and a configured hooks path are not handled; step 2 "nothing is sent anywhere" against step 4 "event ... is queued" is ambiguous for the finding case. Fix: post-commit deletes the marker; skip when a rebase or merge is in progress; the installer detects a hook manager and prints the line to add instead of overwriting. Confidence: medium.

**F33. MCP "same gate" is not defined.** Where: 6.4, 11.4 ("every MCP tool result, passes these checks in order"). Checks 3 (cost reservation) and 4 (send) do not apply to a tool result; check 1 needs provider policy flags, but the assistant's provider is unknown to the core. Fix: define the MCP gate as: content class against a fixed "unknown provider" policy (most restrictive), secret scan, size limit. Confidence: high.

**F34. `2-architecture.md` and.** Where:, "FSRS ... via a library"), 8 (class H for explanations against 9.3 `explain` on class M), 9 ("can be turned off" for masking; file with a secret "goes only to local models"), 12 (still carries a calendar date, see R18);), 3 ("shell hook" in the not-done list). The "Changes made" table does not list these. Fix: edit in the same pass. Confidence: high.

**F35. Principle 10 is not met by the table that follows it.** Where: 2 item 10 ("Every model task has a model-free fallback") against 9.3 (`code_overview`: "none (skipped)"; `generate_course`, `batch_analysis`: "job waits"). Also the reason code `offline` appears in the core-side fallback list (9.6 step 4) although a reachable core cannot be offline. Fix: reword the principle to "a defined degraded behaviour"; rename the reason to `provider_unreachable`. Confidence: high.

## 3. Over-engineering: cut or defer

| # | Part | Simpler alternative | What is lost |
|---|---|---|---|
| O1 | Worker protocol with 16 frame kinds, credit, modes, two protocol versions (6.3) in the first build | M0: the core calls the local OpenAI-compatible endpoint on loopback through the existing adapter. Later: the worker dials in only to register and heartbeat (address, models, mode); the core calls the worker's endpoint over the VPN name with plain HTTP streaming | Works only where the VPN lets the core reach the worker (true inside one mesh); `ensure` and mode become two small HTTP calls on the worker. See question Q-A |
| O2 | Row rule on shared `chunk`, `chunk_annotation`, `emb_*` by link existence (7.2) | No row rule on shared content; the repository only reads chunks through a join on `document_chunk` (already the rule in 7.3) | Database-level defence for text that is by definition not personal; removes R6 |
| O3 | Cost reservation ledger: `reserved` entries, settle, sweeper (9.7) | Check the period total before the call, add actual usage after it | The cap can be overshot by the calls in flight (cents at this scale) |
| O4 | Own job engine: leases, keyed steps, `job_event`, notify fan-out, round-robin by user (8.11) | A job table with status and a JSON checkpoint, one runner loop, progress by polling `GET /v1/jobs/{id}`; or an existing Postgres-backed queue library (verify licence) | Live progress streams; fairness, which three users do not need |
| O5 | Version machinery: `/v2` side by side "for a stated window", minimum version per client kind, `426` flow, worker protocol N and N-1 | One admin updates everything together: keep `X-Kata-Client` and one minimum version | Rolling upgrades nobody will perform |
| O6 | Device stream for every client plus piggyback (6.1, 6.2) | Piggyback on event posts and a poll while a panel is open; streams only for scans and asks | Instant delivery of a nudge to an idle panel |
| O7 | Prometheus endpoint with histograms per route, queue depth, client lag (12.4) | `client.timing` rows in Postgres and a `kata doctor` report; structured logs | Dashboards; a scrape server to run |
| O8 | Taxonomy change log with merge, split, retire functions that rewrite all users (7.4) in version 1 | Rename (ids stable) and retire only; merge by alias; split later | Clean handling of a rare admin action |
| O9 | GPU modes `external`, `draining`, `batch_exclusive`, `mode_request` negotiation (9.5) before S13 | Worker flag "available / not available" set by the existing mode-switch script | Core-initiated batch mode |
| O10 | Contract test layers: recorded request fixtures replayed on both sides, fake core and fake worker, MCP snapshot, breaking-diff gate (13) at the start | Generated types plus one end-to-end smoke per client; add layers when a second implementer or client exists | Early detection of drift that one author rarely causes |
| O11 | Separate `kata-jobs` process with an internal port and service credential (5.2) before S5 load exists | A process pool inside `kata-core` for parsing and embedding; split when a measurement shows API stalls | Isolation of memory spikes from parsing (keep the split if R7 shows gigabytes) |
| O12 | Event envelope extras: per-type schema versions, dead-letter list, drop priorities, 5000-event bounds (6.2) | Versioned type names, drop oldest on overflow | Fine-grained loss control |

Shared chunks by content hash is a binding decision and is not listed; its costs are F6, O2 and R15.

## 5. What is good (do not change)

- Models propose, code decides (principle 6): matches the strongest benchmark result and keeps labels explainable.
- Token login and user-scoped storage from the first slice; "foreign id is `404`".
- Event intake with client-made ids and "do nothing on conflict"; state as a recomputable function of evidence.
- The worker owns its GPU and may refuse; absence is a normal state.
- Pre-commit runs locally and only a finding blocks; bypass is detected after the fact rather than prevented.
- Section 17 and 18 name the open risks plainly, and proposed items are marked as proposed throughout.

