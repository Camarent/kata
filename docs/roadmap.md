# Roadmap

Milestones are ordered by value. Each has a scope and success criteria. Dates are not
committed; the order is.

## Milestone 19: concept model (in progress)

**Scope.** Area > Topic > Concept identity and the per-user data the redesigned UI reads:

- Area, topic and concept identity unique on (area, topic, name) (D54); alias table (D53);
  concept definition line (D55).
- Per-user mark new, learning or known, keyed by concept id; block state derived from concepts.
- Added date, last viewed and relevance fields for sorts (D42).
- Ignored list and hard delete (D55).
- Migrate today's `topic_aliases` and block marks. API and tests only.

## Milestone 25: UI implementation (partial)

**Scope.** Finish the extension UI on the backend from M19 to M24: approved screens (D1 to D58)
on the panel tab, floating card, settings, page overlay and course page. The approved design notes
are in [`design/extension-ui.md`](design/extension-ui.md), section 9; the decision record is in
[`decisions.md`](decisions.md). The UI modules are listed in [`modules/extension.md`](modules/extension.md).

Open:
- Still unmounted (no importer outside its group): the exam run screen `extension/src/ui/panel/examRun.ts`
  (the core has no route that starts an exam run yet). The six page overlays are mounted by
  `extension/src/overlayHost.ts` (`whichOne.ts` is opened from the hover menu `hlMenu.ts`).
  The course page `extension/src/ui/panel/coursePage.ts` is mounted from Open course on the courses tab
  (task-18, `renderCoursesView` in `extension/src/sidepanel.ts`, boot in `extension/src/sidepanelBoot.ts`).
  The exam result screen `extension/src/ui/panel/examResult.ts` is mounted in the panel.
- Track create: Save (`trackCreateHandlers` `onCreate` in `extension/src/sidepanelTracks.ts`) sends `panel:createTrack` with name and deadline, then reloads the Tracks list; a refused save shows the form's error line. Add source and Quiz open their screens.
- Track detail loads the real track (name, deadline, items as sources). The core `Track` has no goal, progress, velocity, finishEarly, tooSlow or dropReason, so `trackDetailView` in `extension/src/sidepanelTracks.ts` gives them neutral empty values: open work, needs core fields.
- Quiz pin: its onStart sends `panel:miniQuiz` (`extension/src/overlayHost.ts:210`) and shows no result; the
  quiz result is not shown yet.
- Image action: `panel:imageAction` returns `ok:false` (`extension/src/backgroundPanel.ts:82`), so the image
  menu action is a dead end. Errors are swallowed at `extension/src/overlayHost.ts:129`, `:211` and `:249`.
- Block menu: bulk buttons are unwired (`extension/src/overlayHost.ts:116`) and New list is hidden (`extension/src/overlayHost.ts:93`).
- No-op handlers (do nothing when called): `onPasteText`, `onChooseFile`, `onUsePage`, `onUseCourse`,
  `onAddSource` (`sourceAdd` handlers in `extension/src/sidepanelBoot.ts`), `onNext` (`quizRun` handlers in `extension/src/sidepanelBoot.ts`), and `onGenerate` (`extension/src/sidepanel.ts:295`).

## Later

Video transcripts, a phone web app, Chrome packaging, passkeys, deeper terminal tracking,
exam mode hardening, a public path for single pages.

Exam mode recorder: a silent recorder of the owner's exam answers. The raw question text is never
stored: the recorder reads question, choices and the owner's pick, analyses them in the background and
keeps only derived data (concepts, topics, weak points). Open: where the exam domain list comes from;
how weak points map to concepts (an existing concept gets "Needs practice", an unknown one is only
proposed after the mode ends).

Latency split: log model and worker wait time apart from server time per request, with a summary, so a
slow model can be told from a server hot spot.

Client and API cleanup: one stable client API surface, a shared client library and versioned types, as
groundwork for the VS Code client and the desktop assistant.

Desktop assistant (future): a Windows app that is always running. A global hotkey starts a push-to-talk
voice question, answered in a small popup. The app transcribes the question, checks the knowledge base,
asks the MCP server of the target app when one exists (for example Blender), takes a screenshot for
context, recommends the hotkey or steps, and writes a remark into the knowledge base. It needs screenshot
capture, speech to text, an MCP client and knowledge lookup through the client API, so the client and API
cleanup comes first. Out of scope until then: an agent that clicks for the user.

Extension UI: design v2 is approved (2026-11-24; navigation, settings, auto-scan and block states;
see [`design/extension-ui.md`](design/extension-ui.md) and [`decisions.md`](decisions.md)).

## Out of scope for now

Voice; a public service (self sign-up, exposure to the public internet); native mobile apps;
publishing any course material; a global review calendar.
