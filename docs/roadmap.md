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
- Unmounted, pending owner decision (no importer outside its group): the page overlays
  `extension/src/ui/overlay/hlMenu.ts` (hover menu), `whichOne.ts`, `blockMenu.ts`, `imageMenu.ts`,
  `listPicker.ts`, `quizPin.ts`; the exam run screen `extension/src/ui/panel/examRun.ts` (the core has no
  route that starts an exam run yet).
  The course page `extension/src/ui/panel/coursePage.ts` is mounted from Open course on the courses tab
  (task-18, `renderCoursesView` in `extension/src/sidepanel.ts`, boot in `extension/src/sidepanelBoot.ts`).
  The exam result screen `extension/src/ui/panel/examResult.ts` is mounted in the panel.
- Unwired track handlers (no-op stubs in `extension/src/sidepanelBoot.ts`): `onAddSource` and `onQuiz` (trackDetail), `onCreate` (trackCreate).

## Later

Video transcripts, a phone web app, Chrome packaging, passkeys, deeper terminal tracking,
exam mode hardening, a public path for single pages.

Exam mode recorder: a silent recorder of the owner's exam answers. Design step first (no code until
the design is approved).

Extension UI: design v2 is approved (2026-11-24; navigation, settings, auto-scan and block states;
see [`design/extension-ui.md`](design/extension-ui.md) and [`decisions.md`](decisions.md)).

## Out of scope for now

Voice; a public service (self sign-up, exposure to the public internet); native mobile apps;
publishing any course material; a global review calendar.
