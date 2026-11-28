Superseded by the redesign decisions 39-55 in decisions.md; replaced after the prototype is approved.
# kata extension: UI design

Status: design for owner review. No extension code changes yet; the implementation follows owner approval.

The static HTML mockups, their shared CSS tokens and the screenshot script were removed. This document is the design spec; the section numbers below (for example 2.15, 2.16 and 3.1) still refer to it. The old screenshots were removed too.

## 1. Principles for the UI

- **Scan only on click or on allowed sites.** The extension reads a page only when the user presses "Scan this page", or when the page matches a site the user has added (an allowed site). Everywhere else, nothing is scanned or stored automatically. The rule comes from principle 5 in `docs/design/detailed-architecture.md` (section 2).
- **The panel shows what the user can do next.** Every state names one next action. Errors say what to do.
- **The page stays quiet.** Highlights mark blocks; they never block reading, never pop up on their own, and never change the lesson text.
- **Labels, not colour alone.** Each mark has an icon and a text label (see section 6).

## 2. Side panel: screens and states

The panel is a sidebar in Firefox (`sidebar_action`) and a side panel in Chrome (`side_panel`). The layout works from a narrow width (about 280 px) to a wide one. Every state below is described in this document.

### 2.1 First run and sign-in

- **First run.** The panel asks for the kata server address, then offers "Sign in". No scan starts. The address field has a label and an example format, not a placeholder alone.
- **Sign-in.** Username and password fields with `autocomplete` set. Errors appear next to the field and in a status line that the screen reader announces. After sign-in the panel goes to Connected idle.

### 2.2 Connected idle

- Shows the current course (or "No course selected"), the "Scan this page" button, and the number of Known, New, Learning and Not tagged blocks from the last scan of this page, if any.
- The "Scan this page" button is the only scan trigger. It is always visible in this state.
- If the current page is an allowed site, the panel says so in plain text ("This site is allowed. Pages here scan when opened.").
- If the current page is not an allowed site, the panel says "Scan this page scans once. Add this site to scan here each time you open it." with an "Add this site" action.

### 2.3 Scanning, with progress

- The "Scan this page" button turns into a progress bar with a count (for example "Scanning topics: 12 of 40 blocks") and a "Cancel" button.
- The progress bar is a determinate progress element with an accessible value. Progress is also announced in a polite live region every 25% step, not on every update.
- The scan target is about 30 seconds. After 30 seconds the panel shows the partial result and says that the scan is still running.

### 2.4 Partial result

- Shown when the scan is cancelled, times out, or the model worker is absent for some blocks.
- Lists the blocks that were tagged, and says how many blocks were not tagged and why (model worker absent, cancelled, or timed out).
- Offers "Scan again" and "Show results so far".

### 2.5 Results, grouped by topic

- Blocks are grouped by topic label. Each group has a heading with its count.
- Groups in order: New, Learning, Known, Not tagged. New comes first because it is what the user needs to read.
- Each block row shows the topic label, a mark (New, Learning, Known or Not tagged, with icon and text), and the buttons of its state (section 2.6). Not tagged rows have no buttons.
- Panel rows use the same outline, tint and tag as the block on the page (section 3). Hovering or focusing a row highlights its block, and the reverse.
- Selecting a block row scrolls the page to that block and focuses it (see section 3).
- Long lessons: blocks are split into sub-blocks and the panel groups them by topic (section 3.1).

### 2.6 Known and new marks

Block states. Three knowledge states and one scan result. The state key is listed in this section.

| State | Mark (icon and label) | Meaning | Buttons |
|---|---|---|---|
| New | "+" and "New", strong: accent colour, filled | Not in review yet. A scan found it as a lesson word. | Start learning; I know this |
| Learning | "~" and "Learning" | In review. Answers still being checked. | Mark known; Back to new |
| Known | check mark and "Known", muted: outline, no tint | Not in review. Set by you, or by the course when its topic moves to known. | Learn again; Back to new |
| Not tagged | dash and "Not tagged", neutral: dashed | Scan result, not a knowledge state. The block was not scanned as a lesson word. Not scored. | None |

- **Known by course.** States are kept per course. The same topic can be Known in one course and New in another. The panel shows the state for the course selected at scan time.
- **Transitions.**
  - New to Learning: Start learning, or answer 2 or 3 in review (Not sure, Not known).
  - New to Known: I know this, or answer 1 in review.
  - Learning to Known: Mark known.
  - Known to Learning: Learn again.
  - Learning or Known back to New: Back to new.
  - Not tagged has no transitions: a new scan can replace it with a state.
- **Undo.** Every change shows an Undo bar. Undo returns the block to its previous state. The bar stays until the next change, not for a fixed time.
- The mark always has a text label. Colour is never the only signal.

### 2.7 "I know this"

- Pressing "I know this" on a block sets the block's topic to known. The row moves from New to Known in place, and a short status line says "Marked as known: <topic>. Undo".
- "Undo" stays until the next change (see the undo rule in section 2.6). The mark can still be changed from the block row.
- The change is sent to the core. If the core is offline, the change is queued locally and the row shows "Saved on this device; will sync".

### 2.8 Review screen (keys 1, 2, 3)

- Opened from the results screen with "Review new blocks". It shows one new block at a time, with its topic and a short sample line from the page.
- Keys: `1` = I know this, `2` = Not sure, `3` = Not known. Each key is shown as a visible button with its key label.
- After each choice the next block loads and focus moves to the next block's heading. At the end the panel shows the count of blocks marked known and a "Back to results" button.
- Keys work only when focus is inside the review screen, so they never fire while the user types in another field.

### 2.9 Courses

- **List.** Shows the user's courses, the current one marked as selected, and a "New course" button. Each course row has "Open" and "Delete".
- **Create.** A name field with a label, then "Create" and "Cancel". An empty name shows an error next to the field. On success the new course opens.
- **Delete.** A confirmation with the course name and the count of marks it holds. The confirmation button is not the default focus. Deleting a course never deletes the user's account data outside that course.
- **Open.** Sets the course as the current one for scans and marks, and returns to Connected idle.

### 2.10 Offline

- Shown when the core cannot be reached. The panel keeps the last known results and course list, labelled "Last updated <time>".
- "Scan this page" is disabled with a reason: "Offline. Scanning needs the kata server." Marks can still be set and are queued.
- A "Try again" button checks the connection. The panel never waits on the core for more than the short timeout before it shows this state.

### 2.11 Sign-in expired

- Shown when the stored token is rejected. Local results and queued marks stay on the device.
- The panel says "Sign-in expired. Sign in again to sync your marks." with a "Sign in" button. Queued marks are not sent until sign-in succeeds.

### 2.12 Empty page

- Shown when the page has no lesson blocks the scanner can read (for example an index page).
- The panel says "No lesson text found on this page." and offers "Scan this page" again, disabled, with a short reason. No error style is used.

### 2.13 Error

- Shown for unexpected failures (for example a bad response from the core).
- The panel shows a short message, a "Details" disclosure with an error code (no stack trace), and a "Try again" button. The error code is the only technical text shown.

### 2.14 Allowed sites

- Reached from "Add this site" or from the Sites screen. The panel proposes a site pattern for the current host (the whole site), which the user can narrow or widen before saving. The pattern rules (URL masks) are in [`docs/design/detailed-architecture.md:228`](detailed-architecture.md#added-sites-url-masks) and section 5.3 of that file.
- Rejected patterns (a bare `*`, a top-level domain only, or an empty host) show a reason next to the field.
- The Sites list shows each allowed site with an enabled switch, Edit and Delete. Deleting a site asks for confirmation.

### 2.15 Navigation map

The map below shows every screen and how a person moves between them.

- **Home (Connected idle).** The main screen. Every other screen is one step away from here.
- **Header.** Always visible on every screen. It holds the course picker (left), the settings entry (right, a gear icon with the text label "Settings") and the auto-scan toggle for the current site (below the header, on Home and Results only).
- **Back.** Every screen except Home has a "Back" button at the top left. It returns to the screen that opened it. Pressing Escape does the same.
- **Tabs.** Two tabs under the header: "Page" (scan, progress, results, detail) and "Review" (the review screen, keys 1, 2, 3). The tabs stay visible on the Page and Review screens.
- **Settings and courses.** "Settings" and the course screen are reached from the header and go back to the screen they came from.

Control placement, in the order a person sees them:

| Control | Where it sits | Screen where it appears |
|---|---|---|
| Scan button ("Scan this page") | Top of Home, under the header, first action in the panel | Home, Results (as "Scan again") |
| Course picker | Header, left, a select with the current course name | Every screen |
| Auto-scan toggle ("Auto-scan this site") | Under the header, below the scan button | Home, Results |
| Settings entry | Header, right, gear icon with the text "Settings" | Every screen |
| Review entry | Second tab, "Review" | Every screen with tabs |

Screens: Home, Scanning, Results, Detail (one block, from a result row), Review, Courses (list, create, delete, open), Course (one course), Settings. Each one is listed in section 2.15 with its id.

### 2.16 Settings page

The settings page is opened from the header entry (section 2.15). The settings page is described in this section.

- **Connection.** Server URL (text field, validated when saved), device label (text field), and "Sign out" (a button that asks for confirmation and removes the device login from this browser).
- **Auto-scan sites.** A list of the sites the user allowed (section 2.17). Each row shows the site pattern and a "Remove" button. Remove deletes the site from the list and stops automatic scans there. Empty state: the text "No sites yet. Turn on Auto-scan this site in the panel on a page you want kata to scan when it opens."
- **Appearance.** Theme choice: "Follow browser", "Light", "Dark". Default is "Follow browser" (section 7).
- **About.** Extension version, the core server version (read from the server when connected), and a link to this design doc's section 6 for accessibility notes. No tracking settings: the extension has none.

### 2.17 Auto-scan this site

- **Off by default.** No site is allowed until the user turns the toggle on. A new install scans only on "Scan this page".
- **The toggle.** The panel shows "Auto-scan this site" for the current site, under the header. On adds the site to the allow list (saves its URL mask and asks the browser for the host permission for that site). Off removes the site from the allow list and gives the permission back where the browser allows it.
- **What runs.** A scan runs when a listed page opens (a full load). It uses the same progress and results screens as a click scan. Pages that are not listed are never scanned on open.
- **Listed site, core offline.** No scan starts. The panel shows the Offline state (section 2.10). The toggle stays on. Nothing is queued for later.
- **Listed site, signed out.** No scan starts. The panel shows the Sign-in expired state (section 2.11). The toggle stays on, and scans resume after sign-in on the next page open.
- **Settings.** Section 2.16 lists the allowed sites with a Remove button, the same way the toggle removes them.
- **Browser differences.** On Firefox and Chrome, the host permission is granted per site and can be revoked (see the browser table in `detailed-architecture.md`, section 5.3). The toggle changes only after the browser grants the permission. If the user refuses, the toggle stays off and the panel says "Permission not given; site not added". If the panel closes while the browser asks, the answer still applies when the panel opens again; the toggle shows the stored state. Edge is not covered by this design yet; it needs its own check before it is listed as supported.

## 3. The page: highlights and detail

The page itself shows marks only on blocks that the scan tagged. The lesson text is never changed except for the highlight style.

| Block state | Look (page) | Label on focus or hover |
|---|---|---|
| New | Strong outline and tint in the accent colour, with a "New" tag at the block start | "New: <topic>. Press I know this in the panel or Enter here." |
| Learning | Outline and tint in the `--color-learning` token, with a "Learning" tag at the block start | "Learning: <topic>. Mark known in the panel to move it on." |
| Known | Muted dotted outline, no tint, with a "Known" tag | "Known: <topic>." |
| Not tagged | No outline; a small neutral dash tag, or a neutral dot in the margin | "Not tagged: scan result only." |

- **Panel rows match the page.** A panel row uses the same outline, tint and tag as its block (the shared colours are defined once). Hovering or focusing a block highlights its row, and selecting a row scrolls the page to its block and focuses it.
- **Exam pages.** No marks and no highlights on exam pages, from page open until the person has finished answering. Exam page detection is an open question in [`docs/backlog.md`](../backlog.md) under "Exam pages (experimental)".

- **Hover or focus detail.** Hovering a marked block, or moving keyboard focus onto it, shows a small detail card with the topic, the mark, and the buttons of its state (section 2.6). The card appears after a short delay and stays while the pointer or focus is on the card. It does not appear when the user is selecting text.
- **Keyboard.** Each marked block is reachable by Tab only through a single "kata highlights" landmark list at the top of the page, not by tabbing through every paragraph. Enter on a list item opens its detail card.
- **Clear.** A "Clear highlights" action in the panel removes the highlights from the page for this tab only. The marks stay saved. Reloading the page brings them back if the page is still scanned.
- **Changing pages.** When the page changes without a full load (single-page navigation), the highlights are removed at once and the panel goes back to Connected idle. A new scan starts only when the user presses "Scan this page", or the page matches an allowed site.
- **Page without a scan.** No highlight is drawn and the page shows nothing from kata.

### 3.1 Long text split

A long block is split into sub-blocks, so a single highlight does not cover a whole page of text. A sub-block is a span inside its paragraph: the text is unchanged, and only the mark is per sub-block. The panel groups the sub-blocks by topic, with one heading per topic and the same row style as in section 3.
## 4. Scan trigger

- The scan starts from the "Scan this page" button in the panel. It is the only trigger on pages that are not allowed sites.
- On an allowed site the scan starts when the page opens, using the same progress and results screens.
- No scan runs in the background, on a timer, or when a page only changes its address without a load, unless the page matches an allowed site.
- The panel shows the scan state for the current tab only.

## 5. Keyboard and focus order

- Panel focus order: the status line, the primary action, the list of blocks or courses, then secondary actions. The order matches the visual order.
- Opening a screen moves focus to its heading. Closing a screen returns focus to the control that opened it.
- Every control works with the keyboard alone. Lists use arrow keys between rows; Tab leaves the list.
- The review screen keys (1, 2, 3) are listed on screen and work only inside that screen.
- Focus is always visible: a 2 px outline with contrast against the background, not removed by any style.

## 6. Accessibility rules

- **Contrast.** Text and interactive parts meet WCAG 2.2 AA: at least 4.5 to 1 for normal text, 3 to 1 for large text and for focus outlines and mark icons against their background. Light and dark themes both meet this.
- **Focus order.** Follows the visual order (section 5). No focus trap except inside the review screen and dialogs, which release focus on close.
- **Keyboard use.** Every action is available without a pointer. No action needs a timed key press or a drag.
- **Not colour alone.** Each mark has an icon and a text label (New, Learning, Known, Not tagged). Errors have a text message and an icon, not only a red border. Highlights on the page have a tag or dot, not only a tint.
- **Reduced motion.** Under `prefers-reduced-motion: reduce` the progress bar does not animate, the detail card fades without motion, and no element slides. Progress is still shown as a number.
- **Screen readers.** Status changes (scan progress, "Marked as known", errors) are announced in one polite live region. Errors that block an action use an assertive region once.
- **Text size and width.** The panel works at 200% text size and at a width of about 280 px without horizontal scrolling. Labels wrap; they are not cut.
- **Touch targets.** Buttons and list rows are at least 44 by 44 CSS px.

## 7. Themes

- Light and dark themes use the same tokens. The panel follows the browser's colour scheme by default.
- Both themes are checked against the contrast rule in section 6.

## 8. Open points for the owner

- Whether "Scan this page" should show a short confirmation the first time per site.
- Whether the review keys (1, 2, 3) should also be shown on the page detail card.
- Final wording of the four marks (New, Learning, Known, Not tagged).

## 9. Approved design notes (owner sign-off)

The owner approved these notes before the UI build (milestone M25). They are the design of record; where a section above differs, the later decision wins.

### 9.1 Decisions D1-D58

# UI redesign decisions (owner, 2026-11-24). Land in docs/decisions.md and docs/roadmap.md when the tree is free.

1. Marks are concept-based. A block's state (New, Learning, Known) derives from the concepts in it; topic only groups blocks. A topic-only highlighter is not the product.
2. Gaps are concepts below the known threshold. Courses are built from concept gaps (already true in the trainer). The scan should offer a course from the gaps.
3. Code today (scout, 2026-11-24): the tag job outputs a topic only (`worker/kata_worker/handlers/tag.py:33`, `core/kata_core/api/routes/jobs.py:123-131`). Known/new is decided from topic marks (`core/kata_core/storage/marks.py:46-52`). The scan never calls `POST /lesson-check` (`extension/src/scanSession.ts:33`); only review does (`extension/src/backgroundPanel.ts` (handler `panel:review`)). No concept is attached to a block anywhere. Update 2026-11-28: the page image menu sends `panel:imageAction`; its `backgroundPanel.ts` row answers "image concepts are not available yet" until the vision work (D33, D16) exists, and makes no lesson-check call.
4. Needed for concept marks: concept extraction in the tag output, a per-block concept list in the scan result, and a lesson-check call on those ids with the states attached to each block. This is a backend milestone, before `ui-impl`.
5. Design process: glossary, journeys, screen inventory (owner sign-off each), one connected prototype, rendered review. v2 mockups are replaced. Prototype is plain HTML plus small JS.
6. Roadmap order: concept scan backend, new UI design, ui-impl. Planning UI (syllabus, tracks, plan, decision points) later, with room for a Plan tab.

7. Course lists (owner, 2026-11-24). One page is not enough to make a course. A person adds missing concepts from many pages to a NAMED LIST (a future course). A Lists screen shows all lists; Generate on a list makes the course. Lists can be created, renamed and deleted, and a concept can be removed from a list. This replaces the single "Make a course from these gaps" button: the scan result offers "Add to list".
8. Backend needed for 7: no list entity exists today (a course takes `concept_ids` at creation, `docs/decisions.md` D5). New: table and API for concept lists (create, rename, delete, add and remove concepts, generate a course from a list).
9. Navigation (owner, 2026-11-24): Lists has its own bottom tab. Other screens carry list hooks: an "Add to list" button on a missing concept, and a marker on a concept showing which lists contain it.
10. Navigation (owner, 2026-11-24, supersedes 9): Courses has its own bottom tab. Lists are not courses: a list is temporary storage of concepts for a future course. Lists live inside the Courses tab as a separate section: Courses first, then "Lists" (drafts) below (owner swapped the order). Several lists exist at the same time. Hooks stay on other screens: "Add to list" on a concept, list marker on a concept. UI must make list vs course unmistakable. Planning scope: open, owner asked what planning gives now.
11. Tracks (owner, 2026-11-24, answers planning scope): design a Tracks tab now, reshaped from the M5 tracks; implementation comes later, after the scan and Lists backend. Owner's example: start a big course in December, finish by end of March, plus an AWS architect exam. Several goals at once, progress tracked per goal, mini quizzes, and a course generated for one part of an exam. Reshape: progress = concepts known / concepts in the goal (from marks); time budget optional.
12. Sources per goal (owner): a goal takes several documents, and more can be added later (two manuals first, a third found afterwards). Adding a source loads the missing topics only. A course may be regenerated after that without losing progress: concept marks are global, so the new course starts from the current state of each concept.
13. Generation mapping of concept states (owner): new = in the course; known = left out; learning = may fit several ladder steps (ladder meaning to verify against dojokit). Configurable at generation time; default is the step of about 3 to 7 days.
14. Lists vs Tracks (owner, 2026-11-24, answers Q5 = A): lists stay separate. A list is a temporary place to organise a future course and works without any track. A course can be one more source of a track. A track can create a list from its missing concepts. Concepts are organised per topic everywhere: "add all concepts of topic TCP, UDP, IP" adds a whole topic at once.
15. Track progress (owner): shows progress and current velocity. Warning when too slow for the deadline; when faster than needed it shows an earlier finish date.
16. Track sources (owner): three ways to add: pasted text, file, current page. New backend need: read PDFs that contain images (diagrams, scanned pages, images on the page), understanding the image content, not only text extraction. Needs a vision-capable model and a cost check; not built.
17. Mini quiz (owner): appears on the web page itself and inside a track. A small mascot button shows when a sizeable new group of concepts is seen. Mascot: a safety pin (not a paperclip), opens and closes; use openly licensed pin images for the look (check each licence, record it). Quiz is small: at most 5 questions, answers prefilled (no typing), short text.
18. Regenerate a course (owner): screen shows what carries over (concept states kept) and what is new (concepts added by new sources). Learning concepts map to a review step, default about 3 to 7 days, changeable at generation.
19. Quiz effect on marks (owner, 2026-11-24, option B): a correct answer moves the concept up one step (New to Learning); a wrong answer never moves it down. Known stays a manual click or a course result. The quiz therefore changes progress.
20. Mascot visibility (owner, 2026-11-24): the safety pin is always visible but quiet, which also shows kata is active on the page. It animates and shows a count only when a sizeable group of New concepts is found. Open question: where quizzes appear on a long page with several places.
21. Quiz places (owner, 2026-11-24, answers Q8): on the page only inline quizzes, a small pin at the end of a section (scroll past, enough New concepts, up to 5 questions, that section only). Overall quizzes (whole page, a track, a topic) live in the panel (extension tab), which the owner expects to keep open. Conflict with 20 (always-visible floating pin) to resolve: does a floating pin stay as an indicator only.
22. Floating mini UI (owner, 2026-11-24, resolves 21): the floating pin stays. Clicking it opens a compact floating panel on the page (no page shift, unlike the side panel) with the most important info and fast commands, for example "Scan page" and "Summary". The side panel stays the full UI (tabs). Technical note for ui-impl: an in-page overlay (content script, isolated shadow root), draggable, closable; side panel opening shifts page content, the overlay does not. Open: what "Summary" means.
23. Summary (owner, 2026-11-24, answers Q10 = C, both): after a scan, Summary gathers all topics found and explains what the whole content is about (the knowledge summary plus a model text summary of the page). Both are offered; check what exists in code before building.
24. Jokes (owner, 2026-11-24): the pin sometimes shows a short, silly joke in a small speech cloud, for fun. Proposed defaults, not yet confirmed: a fixed list shipped with the extension (no model cost), rare, closes by itself, one off switch in Settings, never on exam pages or while a quiz is open.
25. Summary in code today (scout, 2026-11-24): nothing built. Scan result per block has only blockId, topic, known, reason (extension/src/scanSession.ts:9-13). The panel groups rows by topic category (`renderGroups` in extension/src/sidepanel.ts) with no counts. No model job summarises page text; only a bare `summary` task class exists with no handler (worker/kata_worker/providers/base.py:12). Docs list it as served (docs/modules/worker.md:36): stale, fix. Backend needed: topic overview from the concept-based scan (free), plus a new job kind for the page text summary.
26. Joke source (owner, 2026-11-24): fetch jokes one by one from an online source, not only a fixed list. Candidate: JokeAPI (v2.jokeapi.dev), no key, safe mode, 120 requests per minute per IP, code under MIT; the licence of the joke texts and its terms of use are NOT verified (search found no terms text). icanhazdadjoke not checked. Proposed design (not confirmed): kata core fetches, filters (safe mode, language) and caches jokes; the extension asks only the core, never a third party (privacy, no IP leak from every page); shipped list as the offline fallback; off switch in Settings. Check the terms before building.
27. Joke safety (owner, 2026-11-24): jokes from outside are untrusted input (script and prompt injection). Rules proposed, to confirm: (1) shown only via textContent in the isolated shadow root, never innerHTML, no links or images; (2) the core fetches over HTTPS from one configured host, no redirects, timeout, response size cap, schema check, plain text only, length cap, control characters and markup stripped, anything odd dropped; (3) jokes never enter a model prompt or any job input; (4) the extension talks only to the core, the extension CSP allows no remote script or style; (5) all limits from configuration; (6) a security test with hostile joke texts (tags, script, prompt-injection phrases, huge text) before release; (7) sec-auditor reviews it. Safer alternative: a curated list refreshed by us with owner review.
28. Joke source decision (owner, 2026-11-24): live fetch through the core (option A), because the owner cannot review a large list. Use a well-known source and treat every joke as untrusted (rules in 27). Source terms and joke licence still to verify before building; a shipped fallback list stays for offline.
29. Floating card split (owner, 2026-11-24, Q13 = A): the card only reads and starts things (counts, top gaps, Scan page, Summary, Quiz this page, Open panel). Real edits happen in the side panel.
30. Joke cloud (owner, 2026-11-24, corrects 22 and 24): the joke cloud is NOT part of the floating card. It is a random event: a small text field that appears for a short time and closes by itself. Not too often. A cross closes it at once. Settings: on/off, frequency, and the joke source is configurable. Security note: the source choice must be a server-side list of known sources (the core fetches), not a free URL typed by the user (server-side request risk); the rules in 27 apply to every source.
31. First run and connection (owner, 2026-11-24): journey 1 approved. Sign-in stays minimal (Server URL, Code, Device label); no full auth design now because kata is mostly self-hosted. Where the one-time code comes from is unknown: check later. A connection indicator is visible on every screen (panel header, floating pin and card) so a server that is down shows at once.
32. Inline marking (owner, 2026-11-24): marking is available inline on the page for speed. Each concept has small icon buttons: Known, Learning, Add to list. A block (or section) has the same icons and they apply to all its concepts at once. Concepts of one block can have different states. The block state is derived (all known = Known, mixed = shows mixed). Undo stays.
33. Concepts on the page (owner, 2026-11-24, answers the chip question = B, with the block as its own thing): concept words are highlighted in the text (green Known, yellow Learning, grey and others by state: the highlight style the owner liked). Hover on a word shows a mini menu with the icons (Known, Learning, Add to list). The block shows its own border on hover (on a block word), with block-level icons that apply to all its concepts. Images (a big diagram with explanation, a scan): a small pin button on the image; hover opens a menu. If image content is matched to concepts, the menu lists them. If not, the whole image is one block: block buttons plus a list of all its concepts, each with buttons. Risk to design for: a concept may not appear as an exact word in the text; such concepts are listed only in the block menu. Image-to-concept matching needs a vision model (see 16).
34. Lists after generation (owner, 2026-11-24): a list stays after a course is generated from it. It is removed only when the owner removes it. Journeys 1 to 3 approved (journey 2 treated as approved after decision 33).
35. Regenerate and exams (owner, 2026-11-24): regenerate REPLACES the old course (one row, version 2); the owner does not want many courses. Course result today (docs/decisions.md D9): course progress writes trainer evidence; each concept gets a mastery score 0..1; score at or above known_threshold (0.8) means Known, at or above learning_threshold (0.4) means Learning, else New; the mark is written with source `trainer` and journaled. A user mark holds until 3 contrary trainer evidence rows exist, then the trainer overwrites it. New (owner): when creating a course, an option to add an EXAM for the concepts being learned. The exam is 100% confirmation that a concept is learned, with questions different from the practice questions. Whatever dojo says is known must be synced back to kata. Open: needs dojokit support for a separate exam question pool and an explicit known signal (check); exam pass vs the 3-row hold rule.
36. Exam result (owner, 2026-11-24, option A): per concept. Concepts answered right become Known. Concepts answered wrong stay Learning and show as "Needs practice" with a link to the course items for them. Nothing is lowered. Journey 4 approved.
37. Sources into tracks (owner, 2026-11-24): a new source's concepts join the track at once (progress may drop, a banner says why). A BIG upload first shows a confirmation step: a foldable tree of the new topics and their concepts, each removable before it joins. Hierarchy area -> topic -> concept, because a source can be huge: never 1000 concepts in one topic and never a list of 100 topics with 100 concepts each; the tree must be quickly navigable (size limits per level come from configuration). Journey 5 approved.
38. Scan validation (owner, 2026-11-24): a validation step before concepts are made from a page: content that is not teaching material (contact details, a phone number, navigation, cookie and ad text, footers, comments, legal text) must not become concepts or join materials. Backend: a teachable-content check in the tag/extract step, tested with such examples; the same filter applies to uploaded files. Open: schema for the area level (today topics have one level).
39. Review (owner, 2026-11-24): no "due" concept and no "you missed this" nagging; progress and velocity are the signals. Review is self-rating with a "Quiz me" button (option C): the three buttons set the state directly (today `setConcept` sets known/learning/new, extension/src/background.ts:52); Quiz me gives up to 5 prefilled questions for one topic. A correct quiz answer moves New up to Learning (decision 19). Open: which concepts Review lists when nothing is due.
40. Mark known after quiz (owner, 2026-11-24): at the end of a quiz each concept has a manual "Mark as Known" button, so the owner can confirm "I know SYN" and the system holds that state (source user). Quiz alone moves only New to Learning (19).
41. Knowledge sources for quizzes (owner, 2026-11-24): the owner's own materials will not be enough for quiz questions. kata needs a source of general knowledge for questions. Open: the model's own knowledge (cost, accuracy risk, must be labelled) or reference sources fetched with checks; decide with a research pass. Untrusted-text rules (27) apply to anything fetched.
42. Sorting (owner, 2026-11-24): lists in the UI (concepts, topics, lists, courses, tracks, sources) offer sort by name, added date, last viewed, relevance (kata decides from the tracks), each in direct or inverse order. Backend: added date and last viewed fields; a relevance score from tracks. Review (Q: which concepts first) = option A, a tree you pick from with these sorts; no pre-selection (owner did not object).
43. Offline marking (owner, 2026-11-24): option A with a PERSISTENT queue. Marks made while the server is down show at once with a "not synced" dot, are stored in the extension's storage.local (survives browser close, restart, page switch), sent in order when the server answers. Connection indicator shows the count ("server down, 3 not synced"). A queued user mark wins over a trainer update (D9). To verify before ui-impl: whether the extension has an outbox today.
44. Journey 7 (settings and trouble) approved with 43: settings page = connection + sign-out, auto-scan site list with remove, jokes (on/off, frequency, source), appearance; server down disables Scan, Quiz, Generate; signed out shows only the sign-in form.
45. Quiz question sources (owner, 2026-11-24): reference sources give better quality than the model's own knowledge; the model only writes questions from fetched text. Pipeline: core fetches (not the model), allowlisted domains only, plain text kept, size cap, no link following, private and internal IPs blocked (SSRF); model gets text as marked data, no tools, no keys, no access to marks; strict JSON output (question, 3-4 choices, answer index, source quote), core rejects other shapes, URLs, over-long text; grounding check: the quote must appear verbatim in the fetched text; extension renders with textContent only. Model choice reuses existing routing (cloud default when configured, local works; job type plus a setting); questions cached per source. Open: owner's sign-off wording on the model setting.
46. Allowlist tiers (owner, 2026-11-24): Tier 1 authoritative (RFCs and standards, official product docs, the owner's own materials): practice and exams. Tier 2 general reference (Wikipedia and similar, pinned revision, cached): practice only, labelled "general reference", never exams. Defaults fixed in code; owner adds domains per area in Settings (land in Tier 2 with a warning, promotable by hand). Free to read without an account only; no paid or paywalled sources. Check each default source's licence before listing it (Wikipedia CC BY-SA needs attribution and link); show short quotes with a link, never store or republish full text.
47. Isolation (owner, 2026-11-24): no container for fetch and HTML (separate low-privilege process, no secrets, SSRF block, caps). A sandboxed container (no network, read-only filesystem, no keys, file in and text out) for the PDF and image reader, built with that reader. Release default: a stage without a `release:` line is a patch release.
48. Ladder (owner, 2026-11-24, corrects my misreading of 13): the ladder belongs to dojo (steps of about 1 day, 3-7 days, 10 days, ...). Kata has NO due concept and does no scheduling. At course generation a concept's mark picks its starting rung: new = first rung, known = left out, learning = default the 3-7 day rung, choosable per course at generation. To verify in dojokit before design depends on it: rung names and numbers, and how a course item is given a starting rung.
49. Course generation rung (owner, 2026-11-24): option A. One setting on the Generate course screen, "Learning concepts start at: 3-7 days" (default), applies to the whole course; a single concept can be changed afterwards in the course preview.
50. Jokes and focus mode (owner, 2026-11-24): jokes default ON, at most once per 2 hours, never during a quiz, while marking, or in focus mode; settings: off switch, interval, source (24, 26, 28). Focus / Exam mode: one manual toggle button (floating card and panel); while on, no jokes, no pin nudges, no inline quiz offers, no page highlights, no inline mark buttons (marking is off); scanning still works, results show only in the panel; the connection indicator stays; auto-ends after a chosen time (default 3 hours) so it is not forgotten. Exam is not auto-detected. "This is exam results" button: records an exam result (date, pass/fail, score) on the track goal; owner leans to also feed progress. Open: A record only vs B record plus per-domain scores proposing Known to Learning changes the owner confirms (my advice: build A first, B later).
51. Exam results (owner, 2026-11-24): option B wanted: record result (date, pass/fail, score) plus optional per-domain scores; kata proposes moving concepts of weak domains from Known to Learning, owner confirms each. Owner: unsure how well it can work, worth trying. Build order: record first, per-domain proposals next. Needs a mapping from exam domains to areas, topics or concepts (a source of the exam's domain list, e.g. a track source or a syllabus); if no mapping exists, the owner picks topics by hand. Open: where the domain list comes from.
52. Summary button (owner, 2026-11-24): the floating card has ONE "Summary" button; its view holds both the knowledge summary and the page text summary, each labelled. The glossary ban on a bare "Summary" applies to text that does not say which view it means.
53. Concepts and aliases (owner, 2026-11-24): a segment-level term that only combines two concepts is not its own concept. SYN and ACK stay separate concepts (each is one flag, ACK recurs in every later segment). "SYN-ACK" and "Three-way handshake" are one concept: Three-way handshake; "SYN-ACK" is an alias that highlights on the page and opens that concept. Concept extraction must merge aliases into one concept. Consequence: SYN-ACK cannot be marked Known alone. Applies to the prototype sample, glossary (term Alias) and the backend concept extraction.
    Backend note (D53): today only topics have aliases (topic_aliases, storage/taxonomy.py). Milestone must add concept aliases: per-concept alias list (case-insensitive lookup, shared or private like topics), extraction returns canonical name plus alias words and merges into the existing concept, scan output carries the written word plus concept id.
54. Concept identity (owner, 2026-11-24): a concept is identified by area, topic and name together. The same word under different area or topic is a different concept with its own mark. Scan first classifies the page into area and topic (candidates: the user's existing taxonomy, then new ones), then extracts concepts and resolves aliases within that area and topic. Owner accepts the extra classification work. When the model cannot decide, the hover menu shows "Which one?" with the candidates; the pick is remembered for that page's topic. Menu item "Not this meaning" reassigns a highlight to another concept and teaches the alias. Backend: unique key (area, topic, name); alias unique per (area, topic); page classification result cached per page; classification is the first model step of a scan and needs an evaluation set. Supersedes the 'topic only groups' wording where identity is concerned: topic still does not decide block state.
55. Prototype review round 1 (owner, 2026-11-24). Colors, style and block order approved. Changes: (a) state buttons are icons (Known, Learning, New) with tooltip and accessible label, everywhere. (b) concept menu shows a one-line definition (generated at extraction); 'Not this meaning' stays as an icon, only shown with a definition present. (c) blocks, borders and menus never shift or cover page text. (d) requirement: pages are dynamic; the extension rescans on page change (mutation watch, debounced) and keeps marks by concept id. (e) quiz questions must not contain or imply the answer; generator rule: answer words and obvious derivations must not appear in the question stem, checked after grounding. (f) all actions are local: next to the clicked item, no cursor travel across the screen; list picker opens beside its button. (g) spacing of dropdowns and menus fixed everywhere incl. Focus mode. (h) scan result concept rows at most 2 lines, icon buttons. (i) Review tree collapsed by default with counts, except area and topic of the open page; Collapse all / Expand all; clicking a concept never expands the tree. (j) wrong items: separate 'Delete' (removes from data, a later scan may bring it back as New) and 'Ignore from now on' (hidden, never detected again, managed in a list in Settings with restore), for concepts and topics, with undo. (k) scale to 1000+ concepts: search box, state filter icons, 'Only this page' filter.
Verified in dojo-kit docs (2026-11-24, audit): default review ladder is 0, 1d, 5d, 10d, 30d (5 stages, symbol DEFAULT_LADDER in the dojo-kit repo, srs module; per-unit override via srs.ladder); stages are numbered, not named; a unit counts as learned at stage 4 (learned-stage rule in the dojo-kit authoring guide). Known signal: placement answers known/again (dojo-kit architecture doc, symbol applyPlacement) and session setting knownDistinct; no other known status. No separate exam question pool documented (examOnly units and topics poolAspects are different features). Effect on D48/D49: the starting rung at course generation is a dojo stage number, not '3 to 7 days'; D35 exam support needs a dojo change or a kata-side exam flow.

56. (2026-11-24, owner round 2) Every menu that sets a concept state (hover menu, block menu, scan row, Review row, image pin menu, quiz end) has a fourth icon button "New" that resets the concept to new. Marking is always reversible from the same menu; image blocks included. Same icon set and order everywhere: New, Learning, Known.

57. (2026-11-24, owner round 2) Pin mini-menu. (a) Undo is universal: one Undo button lives in the always-visible pin mini-menu, shows the last action, and is removed from the per-concept and image menus (toast stays as confirmation only). (b) The pin is draggable; its position is remembered per device (shared across sites), clamped to the viewport on resize; the prototype only keeps it in memory. (c) The cross never makes the pin disappear: it collapses the card to the pin icon button; clicking the pin icon opens it again. (d) The Kata card has its own collapse cross.

58. (2026-11-24, owner) Exams. An exam inside a dojo course stays in dojo and runs there; dojo has the wider question types. An exam the user makes on a web page is a separate thing: kata only grabs its results, with a confirm step before marking Known (D35 holds: confirm Known only). Kata does not author exams itself for now (debatable, needs an experiment). Quizzes (D45-D47) stay in kata. Open: owner floated renaming Focus mode to "exam mode"; not renamed until decided.

### 9.2 Glossary

# UI glossary (draft 4)

Source: `.notes/ui-redesign-decisions.md` (decisions 1 to 54, authoritative; later beats earlier) and draft 1 (code cites). "D<n>" = decision number. Status: "code" = exists today; "backend" = needs a backend milestone before `ui-impl`; "design" = designed now, built later.

## 1. Terms

| Term | Meaning | States / fields | Where it shows | Status |
|---|---|---|---|---|
| Area | Top level of the hierarchy: groups topics so a huge source stays navigable. | Size limits per level from configuration. | Confirmation tree for big uploads; sources, tracks. | Backend: topics have one level today, schema for area open (D37, D38). |
| Topic | A group of concepts and blocks. It only groups; it does not decide a block's state. | Name; added date, last viewed (for sorting). | Tree level under area; "add all concepts of topic TCP, UDP, IP" adds a whole topic (D14). | Code: topics and topic marks exist (D3). Added date and last viewed need backend (D42). |
| Concept | The unit of knowledge. Marks, gaps, lists, courses, quizzes and tracks all work on concepts. A concept is identified by area + topic + name (D54): the same word under another area or topic is a different concept with its own mark. One concept can have aliases (D53); SYN and ACK stay separate concepts, but SYN-ACK and Three-way handshake are one (D53). | New, Learning, Known. Mark source: user, trainer. Mastery 0..1 from course evidence: >= 0.8 Known, >= 0.4 Learning, else New (D35). | Highlighted word on the page (D33); rows in panel; list marker shows which lists hold it (D10). | Code: concepts and `concept_marks` exist (D1, D35). No concept is attached to a block yet; backend needed (D3, D4). |
| Alias | Another word on the page that points to the same concept. Extraction merges aliases into one concept; a mark applies to that one concept. | Concept name plus a list of alias words, for example Three-way handshake: SYN-ACK, handshake (D53). | Highlighted like the concept; hover or click opens the concept menu with the line "Also written: SYN-ACK". | Backend: alias merge in extraction needed (D4, D53). |
| Which one? | The choice the hover menu shows when the scan cannot decide which concept a word means (D54). Lists the candidate concepts, each line: concept name plus "Area > Topic". Picking one is remembered for that page's topic and applies the mark target. The menu item "Not this meaning" moves a highlight to another candidate and teaches the alias; without another candidate it says "No other meaning known". | Candidates; chosen concept; remembered per page topic. | Ambiguous highlights (dashed underline, no state colour); every concept menu title shows "Area > Topic" as a second line. | Backend: candidate lists in extraction (D4, D54). |
| Block | A page element (or image, or section) with its own border on hover and block-level icons that act on all its concepts at once. | State is derived from its concepts: all Known = Known, mixed = shows mixed (D32). | Hover border, block icons; image gets a small pin button and menu (D33). | Code: block scan exists, state from topic marks only (D3). Concept-based state needs backend (D1, D4). Image-to-concept matching needs a vision model (D33, D16). |
| Scan | Reads the page, makes concepts from teaching content only, shows New, Learning, Known marks. Offers "Add to list". | Per block today: blockId, topic, known, reason (D25). Auto-scan site list (D44). | Floating card "Scan page"; panel; settings site list. | Code: scan by topic exists. Backend: concept extraction in tag output, per-block concept list, lesson-check call (D4); teachable-content check (D38). |
| Summary | After a scan: all topics found, what the whole content is about. The floating card has ONE button "Summary" (D52); its view holds two parts, each labelled: "Knowledge summary" and "Page text summary". Only that button label may say "Summary" alone. | Knowledge summary: topic overview (free, from concept scan). Page text summary: model text of the page (new job). | Floating card button "Summary" and its view; panel Summary tab. | Backend: nothing built; no handler for a `summary` task (D23, D25). |
| List | A named, temporary place to collect concepts for a future course. Works without any track. Several can exist. Not a course. | Created, renamed, deleted; concept added or removed. Stays after a course is generated from it; removed only by the owner (D34). | Section "Lists" below Courses in the Courses tab (D10). "Add to list" icon and list marker on concepts (D9, D10). A track can create a list from its missing concepts (D14). | Backend: no list entity today; table and API needed (D7, D8). |
| Course | A generated study product from concepts. | Regenerate replaces the old course (one row, version 2) (D35). Mapping: New in course, Known left out, Learning starts at the 3-7 day step, set once on the Generate course screen ("Learning concepts start at: 3-7 days", default), applies to the whole course; one concept can change afterwards in the course preview (D48, D49). Can have an exam option (D35). | Own bottom tab Courses, first section (D10). Regenerate screen shows what carries over and what is new (D18). | Code: courses from concept ids exist (D2). Generate from a list: backend (D8). Exam option: needs dojokit check (D35). |
| Exam | Option at course creation. Questions differ from practice questions. Passing confirms a concept is learned. Questions come from Tier 1 sources only, never Tier 2 (D46). | Per concept: right = Known; wrong = stays Learning, shown as "Needs practice" with link to course items. Nothing is lowered (D36). | Course; result screen. | Backend: needs dojokit separate exam pool and explicit known signal, synced back to kata (D35). Open: exam vs 3-row hold rule. |
| Quiz (mini) | Short quiz: at most 5 questions, answers prefilled (no typing), short text. | Correct answer moves New to Learning; wrong never lowers (D19). End of quiz: manual "Mark as Known" per concept, owner confirms "I know SYN", source user; quiz alone never sets Known (D40). Questions come from fetched reference text, grounded by a verbatim quote (D45). | Inline pin at the end of a section on the page (D21); whole page, a topic or a track from the panel; "Quiz me" in Review for one topic (D39); floating card "Quiz this page" (D29). | Backend: not built. Question source decided: fetched reference sources, model writes only from that text (D41 resolved by D45, D46); needs the fetch process (D47). |
| Track | A goal container with progress. Several tracks at once. Reshaped from M5 tracks. | Progress and velocity; optional time budget; deadline. Sources: pasted text, file, current page, a course (D14, D16). | Tracks tab. | Design now, build later after scan and Lists backend (D11). Reading PDFs with images needs a vision model and cost check (D16). |
| Source | A document, page, text or course that feeds a track. More can be added later; adding loads the missing topics only. | Three ways in: pasted text, file, current page (D16). Big upload shows a foldable confirmation tree, each item removable (D37). | Track screen; sorting by name, added date, last viewed, relevance (D42). | Design; backend needed (D12, D16, D37). |
| Goal | What a track aims at, for example a big course by end of March, or an AWS architect exam (D11). | Concepts in the goal; deadline. | Tracks tab. | Design (D11). |
| Progress | Concepts Known / concepts in the goal, from marks. | A new source's concepts join at once; progress may drop and a banner says why (D37). | Track screen. | Design (D11, D37). |
| Velocity | Current speed of progress. | Warning when too slow for the deadline; earlier finish date when faster than needed (D15). | Track screen. | Design (D15). |
| Review | Self-rating of a concept. Three buttons set the state directly; "Quiz me" gives up to 5 questions for one topic. A tree you pick from, with sort options; no pre-selection, no "due" list (D39, D42). | New, Learning, Known. | Review screen. | Code: `setConcept` sets known, learning, new (D39). "Quiz me" backend (D45). |
| Device | An enrolled browser. | Server URL, Code, Device label (D31). | Sign-in; Settings (connection, sign-out) (D44). | Code (draft 1: `/auth/enrol`, `/auth/devices/{id}`). |
| Connection indicator | Shows at once if the server is down. Shows the count of unsynced marks ("server down, 3 not synced"). | Up, down, count. When down: Scan, Quiz, Generate are disabled (D44). | Every screen: panel header, floating pin and card (D31, D43). | Design (D31, D43). |
| Pin (mascot) | A safety pin (not a paperclip), always visible but quiet; shows kata is active. Animates and shows a count only when a sizeable group of New concepts is found. Click opens the floating card. Its cross collapses it to a small icon button; the icon opens it again (D57). | Opens and closes. Openly licensed images; check and record each licence (D17). | Floating on the page; an inline pin at section ends for quizzes (D21). Draggable, closable overlay in a shadow root (D22). | Design; not built (D20, D22). |
| Floating card | Compact card from the pin: reads and starts things only (counts, top gaps, Scan page, Summary, Quiz this page, Open panel). Edits happen in the side panel (D29). | None. | On the page; no page shift (D22). | Design (D22, D29). |
| Joke cloud | A random event: a small text field with a short joke, closes by itself, a cross closes it at once. Not part of the floating card (D30). | Default ON, at most once per 2 hours; never during a quiz, while marking, or in focus mode. Settings: off switch, interval, source (D30, D44, D50). Source from a server-side list of known sources; the core fetches (D28, D30). | Near the pin. | Backend: not built. Source terms unverified (D26, D28). Safety rules in D27 still to confirm. |
| Offline queue | Marks made while the server is down show at once with a "not synced" dot. Stored in extension `storage.local`, sent in order when the server answers. A queued user mark wins over a trainer update. | Not synced, synced. Persistent: survives browser close, restart and page switch; sent in order. | Marks on page and panel; connection indicator count ("server down, 3 not synced"). | Design. Verify whether an outbox exists today (D43). |
| Focus mode | One manual toggle (button in floating card and panel) for exams or deep work. While on: no jokes, no pin nudges, no inline quiz offers, no page highlights, no inline mark buttons (marking is off). Scan still works; results show only in the panel. Not auto-detected (D50). | On, off. Auto-ends after a chosen time (default 3 hours) so it is not forgotten. Connection indicator stays. | Floating card, panel. | Design (D50). |
| Exam result | A recorded exam outcome on a track goal, by the button "Enter exam results". Option B: date, pass/fail, score, plus optional per-domain scores. kata proposes moving concepts of weak domains from Known to Learning; owner confirms each. Build order: record first, per-domain proposals next (D50, D51). | Date, pass/fail, score, per-domain scores (optional). Without a domain mapping the owner picks topics by hand (D51). | Track goal. | Design. Needs a mapping from exam domains to areas, topics or concepts (D51). Owner unsure how well it works; worth trying. |
| Source tier | Tier 1 authoritative (RFCs and standards, official product docs, the owner's own materials): practice and exams. Tier 2 general reference (Wikipedia and similar, pinned revision, cached): practice only, labelled "general reference", never exams (D46). | Allowlist: defaults fixed in code; owner adds domains per area in Settings, they land in Tier 2 with a warning and can be promoted by hand. Free to read without an account only. | Settings (allowlist per area); question source label; short quotes with a link. | Design. Check each default source's licence first (Wikipedia needs attribution and link). Never store or republish full text (D46). |
| Learning start step | Where a Learning concept starts in a generated course: "Learning concepts start at: 3-7 days" (default). New starts at the first step; Known is left out. kata does no scheduling of its own (D48, D49). | One setting for the whole course; a single concept can change afterwards in the course preview. | Generate course screen; course preview. | Design. Verify in dojokit: step names and numbers, and how a course item gets a starting step (D48). |
| Sort options | Every list (concepts, topics, lists, courses, tracks, sources) sorts by name, added date, last viewed, or relevance (kata decides from the tracks), each with a reverse button (D42). Labels per key: name "A to Z" / "Z to A"; added date "Newest first" / "Oldest first"; last viewed "Most recent first" / "Least recent first"; relevance "Most relevant first" / "Least relevant first". | Sort key, direction. | All lists; Review tree. | Backend: added date, last viewed, relevance score from tracks (D42). |
| Mark as Known (after quiz) | Manual button at the end of a quiz, per concept. Owner confirms the state; source user (D40). | Known, source user. | End of quiz screen. | Design (D40). |
| New (reset) | Puts a concept back to state New. Icon button "New" (tooltip and aria-label "New") in every menu that sets a state, in the order New, Learning, Known: scan rows, Review rows, highlight menu, block menu, image menu, quiz end ("Mark as New"). Pressing it shows a toast; Undo is in the pin (D57); no confirm step (D56). | New, source user. | Scan results; Review; highlight menu; block menu; image menu; quiz end. | Design (D56). |
| Panel | The browser side panel with the tabs (Scan results, Courses, Tracks, Review). Edits happen here. UI text says "Panel" always, never "Side panel" (D29 wording stays in notes only). | Open, closed. | "Open panel" on the floating card; "Show in panel"; "Back to panel". | Code: side panel exists today; wording only (D29). |
| Course page | A full browser page (not the panel) that holds course items and the exam run, so a long study session has room. | Items, exam run, exam result. | Opened from a course; "Open course items"; "Back to panel". | Design (D35). |
| Settings | One settings page: Connection, Auto-scan sites, Jokes, Appearance, Allowed sources. Opened from the panel header and the connection indicator. | Sections as listed (D44). | Settings page; "Open settings". | Design (D43, D44). |
| Appearance | Settings section for how kata looks: theme (Light, Dark, System), later highlight style. | Theme; highlight style (design only). | Settings page. | Design (D44); stored in extension `storage.local`, no code today. |
| Auto-scan sites | Settings list of sites that scan by themselves when opened; each can be removed. | Site address (domain); add, remove. Empty by default. | Settings page. | Code in extension (D44); extension `storage.local`, no backend. |
| Allowed sources | Settings list of domains that quiz questions may be fetched from, per area. Shows Tier 1 and Tier 2. | Domain, tier, area. Added domains land in Tier 2; "Make Tier 1" promotes by hand (D46). | Settings page. | Design (D46). |
| Tier 1 | Authoritative source tier: RFCs and standards, official product docs, the owner's own materials. Used for practice and exams. | Label on questions and in Allowed sources. | Quiz and exam footer; Allowed sources. | Design (D46). See Source tier. |
| Tier 2 | General reference tier (Wikipedia and similar). Practice only, labelled "general reference", never in exam text. | Label on questions and in Allowed sources. | Quiz footer; Allowed sources. | Design (D46). See Source tier. |
| Domain | Two meanings, kept apart by a qualifier. (1) Web domain: a site address in Allowed sources and Auto-scan sites ("Add domain"). (2) Exam domain: a scored part of an exam in "Domain scores". UI text says "domain" only next to one of these two contexts. | Web domain: address. Exam domain: name, score (optional). | Allowed sources; Auto-scan sites; exam result entry. | Design (D46, D51). Open: exam domain list source. |
| Time budget | Optional time the owner can give a track; set when creating a track. Meaning of the number (unit, per week or total) is open. | Optional field next to the deadline. | New track. | Design (D11). Open: unit of the time budget. |
| Sign in | Enrol this browser with Server URL, Code and Device label. Button and screen title. | Loading, error ("Could not sign in"). | Sign-in screen; Signed out screen. | Code (draft 1: `/auth/enrol`) (D31). |
| Sign out | Remove this device's enrolment. Confirmation warns that unsynced marks are lost. Button and screen title. | Error ("Could not sign out"). | Connection settings; Sign out screen. | Code (draft 1: `/auth/devices/{id}`) (D44). |
| Not synced (dot) | Small dot on a mark made while the server is down. "Not synced" is the only wording; also the count in "3 not synced". | Not synced, synced. | Marks on page, panel, Review, quiz result. | Design (D43). See Offline queue. |
| Mixed (block state) | Block state when its concepts differ (some Known, some not). Derived, never set by hand (D32). | Mixed, plus New, Learning, Known. | Block border, block menu. | Backend with concept-based state (D1, D32). |
| Needs practice | Wording for a wrong exam answer on a concept: it stays Learning. Never "Failed" (D36). | Shown with a link to course items. | Exam result. | Design (D36). |
| Ignore | Hides a concept or a topic from now on: it vanishes from scan results and highlights and is never found again, and joins the Ignored list. Icon button "Ignore from now on" with tooltip; inline confirm step, then a toast, Undo in the pin (D57), no modal. Restore each item in Settings, "Ignored words and topics" (D55). | Ignored, restored. | Highlight menu, Review rows and topic headers, Settings. | Design (D55). |
| Delete | Removes a concept or a topic from the collection. Icon button "Delete" with tooltip; inline confirm step, then a toast, Undo in the pin (D57), no modal. A later scan can bring it back as New. Not the same as Ignore (D55). Deleting a list keeps its own screen. | Deleted, brought back by Undo or by a later scan as New. | Highlight menu, Review rows and topic headers. | Design (D55). |
| Definition | One line that says what a concept means. Shows under the concept name in the highlight menu and in Review. "Not this meaning" shows only when a definition is shown (D55). | One line of text. | Highlight menu; Review row. | Design (D55); needs backend field. |
| Undo | Reverts the last action: an inline mark, a block or image mark, a reset to New, a delete or an ignore. Icon button in the pin, always visible; dimmed when nothing is left to undo. Its title names the action ("Undo: marked Known"). The toast is plain text, no Undo button (D57). | One step; works offline (queue entry removed). | Pin, expanded (the Undo icon). | Design (D33, D43, D56, D57). |
| Collapse | Shrinks the pin or the kata card to the small pin icon button (safety pin icon), and back. A cross on the pin and a cross on the kata card collapse; Esc collapses the kata card; Enter or Space on the icon opens it again. The pin never vanishes (D57). | Collapsed, expanded. Pin position is kept per device and clamped inside the viewport (D57). | Pin, kata card, collapsed pin screen. | Design (D57). |
| Regenerate | Replaces a course by a new version of the same course. Never creates a second course (D35). | Shows what carries over and what is new (D18). | Course preview; Regenerate course screen. | Design (D35, D18). |
| Version 2 | Label of a regenerated course: same row, replaced content (D35). Next regeneration gives version 3, same wording. | Version number. | Courses tab; course preview; Regenerate screen. | Design (D35). |
| Learning concepts start at | Label of the one setting on Generate course: "Learning concepts start at: 3-7 days" (default). Same as Learning start step. | See Learning start step. | Generate course; Regenerate course; course preview. | Design (D48, D49). |
| Quiz question source (label only) | Setting wording for the model that writes quiz questions: reuses existing routing (cloud default when configured, local works). UI shows questions with a source link and tier label, not the pipeline steps (D45, D46). | Model setting; wording not signed off. | Settings; question footer. | Design. Open: wording of the model setting (D45). |

## 2. Hierarchy

```
Area
  Topic
    Concept     (state: New / Learning / Known)
      Block     (state derived from its concepts)
```

- Blocks live on a page; a block holds several concepts, which may differ in state (D32).
- Topic only groups. Block state comes from concepts (D1).
- Never 1000 concepts in one topic, never 100 topics with 100 concepts each (D37).
- Area level is not in the schema today (D38).
- Identity is area + topic + name (D54): "Window" under Networking > TCP and "Window" under Software > UI are two concepts, each with its own mark.
- List, Course, Track, Source sit beside this hierarchy and all hold concepts (D7, D12, D14).

## 3. Words not to use in UI text

- "due" or "due concept". No due concept (D39).
- "You missed this" or any nagging. Progress and velocity are the signals (D39).
- "ladder" or rung names, as if kata schedules. kata does no scheduling; the UI says "start at 3-7 days" (D48, D49).
- "marks move" or any wording that says a wrong answer lowers a state. Nothing is lowered (D19, D36).
- "Make a course from these gaps" as a scan button. Replaced by "Add to list" (D7).
- Calling a list a course, or "Lists" as its own bottom tab. Lists are drafts inside the Courses tab (D10).
- "topic" for a block's state (known/new by topic). State is concept-based (D1).
- "paperclip" for the mascot. It is a safety pin (D17).
- "regenerate creates a new course" or "many courses". Regenerate replaces; version 2 (D35).
- "Exam" for a mini quiz, or the reverse. Quiz moves New to Learning only; exam confirms Known (D19, D35).
- "Failed" for a wrong exam answer. Use "Needs practice" (D36).
- "due" in any form (already above); "paid source" or any paid or paywalled source (D46).
- Any text implying exams use Tier 2 or "general reference" sources. Exams use Tier 1 only (D46).
- "Side panel" in UI text. Say "Panel" (one word for one thing).
- "Summary" alone anywhere except the one card button labelled "Summary" (D52). Its view and every other place say "Knowledge summary" or "Page text summary" (D23, D52).
- Two summary buttons on the floating card. One button "Summary" (D52).

## 4. Conflicts between decisions (resolved, for the record)

- D9 superseded by D10 (Lists tab vs section in Courses).
- D20 (always-visible pin) vs D21: resolved by D22; pin stays, opens the floating card.
- D22/D24 (jokes in the card) corrected by D30: joke cloud is a separate event.
- D24 (fixed list) superseded by D26 and D28 (live fetch via core, fixed list is offline fallback).
- D2 (scan offers a course from gaps) replaced by D7 (Add to list).
- D12 and D18 say "new course" on regenerate; D35 says replace. Use D35.
- D39 lists Review contents as open; D42 chose a tree with sorts (owner did not object).
- D13 ladder reading corrected by D48: the ladder belongs to dojo; kata only picks the start step.
- D41 (quiz knowledge source open) resolved by D45 and D46.
- D23 offers both summaries; D52 puts them behind one card button "Summary", each part labelled inside.
- Panel vs side panel: D29 and D44 notes say "side panel"; UI text uses "Panel" only (this draft).
- D50 sets joke defaults, closing the D24 default question.
- D50 leaves exam result as record only (A) or A plus B; D51 chose B, built in two steps.

## 5. Open questions

1. Where does the one-time sign-in code come from? Check later (D31).
2. Joke source: terms of use and joke text licence unverified; JokeAPI and icanhazdadjoke candidates; D27 safety rules to confirm (D26, D28).
3. Summary: what exists in code; backend job for the page text summary not built (D22, D25, D52).
4. Exam: does dojokit support a separate exam pool and an explicit known signal? Exam pass vs the 3-row hold rule (D35).
5. Verify in dojokit: step names and numbers, and how a course item gets a starting step (D48).
6. Schema for the area level; per-level size limits from configuration (D37, D38).
7. Does the extension have an outbox today? Verify before `ui-impl` (D43).
8. PDF and image reading: vision-capable model and cost check (D16, D33).
9. A concept may not appear as an exact word in the text; such concepts show only in the block menu (D33).
10. Planning UI (syllabus, plan, decision points) later; leave room for a Plan tab (D6).
11. Pin image licences: check and record each (D17).
12. Where does the exam domain list come from (track source, syllabus, or owner picks by hand)? (D51)
13. Focus mode auto-end default of 3 hours: confirmed? (D50)
14. Wording of the model setting for quiz questions (D45).
15. Licence check of each default allowlist source (D46).
16. Time budget: unit and meaning (per week or total) (D11).

### 9.3 Screen inventory summary

Source: the approved screen inventory (48 screens). Each surface and its count:

| Surface | Screens |
|---|---|
| Panel tab | 22 |
| Floating card | 9 |
| Settings page | 8 |
| Page overlay | 6 |
| Course page | 3 |
| Total | 48 |

M26 adds config keys only (`[models]`, `[provider_openai]`, `vision`) and changes no UI (the needs-cloud verdict follows the `[models]` cloud provider token, so the existing needs-cloud messages are unchanged); see `docs/backlog.md`, `docs/modules/worker.md` and `docs/roadmap.md` for the M26 notes.
