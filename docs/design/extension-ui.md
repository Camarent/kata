# kata extension: UI design

Status: design for owner review. No extension code changes yet; the implementation follows owner approval.

Visual mockups (static HTML and CSS, open from disk, no network):

- [Side panel, all states](extension-ui/panel-states.html): every panel state side by side, light and dark.
- [Sample lesson page, highlights](extension-ui/lesson-page.html): the page highlights in each state, light and dark, at narrow panel width.
- Shared tokens: `extension-ui/tokens.css`.

The mockups use generic sample text only. They show no real site and no personal data.

## 1. Principles for the UI

- **Scan only on click or on allowed sites.** The extension reads a page only when the user presses "Scan this page", or when the page matches a site the user has added (an allowed site). Everywhere else, nothing is scanned or stored automatically. The rule comes from principle 5 in `docs/design/detailed-architecture.md` (section 2).
- **The panel shows what the user can do next.** Every state names one next action. Errors say what to do.
- **The page stays quiet.** Highlights mark blocks; they never block reading, never pop up on their own, and never change the lesson text.
- **Labels, not colour alone.** Each mark has an icon and a text label (see section 7).

## 2. Side panel: screens and states

The panel is a sidebar in Firefox (`sidebar_action`) and a side panel in Chrome (`side_panel`). The layout works from a narrow width (about 280 px) to a wide one. Every state below has a heading in the mockup `panel-states.html`.

### 2.1 First run and sign-in

- **First run.** The panel asks for the kata server address, then offers "Sign in". No scan starts. The address field has a label and an example format, not a placeholder alone.
- **Sign-in.** Username and password fields with `autocomplete` set. Errors appear next to the field and in a status line that the screen reader announces. After sign-in the panel goes to Connected idle.

### 2.2 Connected idle

- Shows the current course (or "No course selected"), the "Scan this page" button, and the number of known, new and untagged blocks from the last scan of this page, if any.
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
- Groups in order: New, Known, Untagged. New comes first because it is what the user needs to read.
- Each block row shows the topic label, a mark (New, Known or Untagged, with icon and text), and an "I know this" button for blocks that are not known yet.
- Selecting a block row scrolls the page to that block and focuses it (see section 3).

### 2.6 Known and new marks

- **New**: strong mark: filled icon, bold label "New", and the accent colour.
- **Known**: muted mark: outline icon, label "Known".
- **Untagged**: neutral mark: dashed icon, label "Not tagged". Untagged blocks are not scored.
- The mark always has a text label. Colour is never the only signal.

### 2.7 "I know this"

- Pressing "I know this" on a block sets the block's topic to known. The row moves from New to Known in place, and a short status line says "Marked as known: <topic>. Undo".
- "Undo" is available for 10 seconds. After that it is removed from the status line; the mark can still be changed from the block row.
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

## 3. The page: highlights and detail

The page itself shows marks only on blocks that the scan tagged. The lesson text is never changed except for the highlight style.

| Block state | Look (page) | Label on focus or hover |
|---|---|---|
| New | Strong outline and tint in the accent colour, with a "New" tag at the block start | "New: <topic>. Press I know this in the panel or Enter here." |
| Known | Muted dotted outline, no tint, with a "Known" tag | "Known: <topic>." |
| Untagged | No outline; a small neutral dot in the margin | "Not tagged." |

- **Hover or focus detail.** Hovering a marked block, or moving keyboard focus onto it, shows a small detail card with the topic, the mark, and an "I know this" button. The card appears after a short delay and stays while the pointer or focus is on the card. It does not appear when the user is selecting text.
- **Keyboard.** Each marked block is reachable by Tab only through a single "kata highlights" landmark list at the top of the page, not by tabbing through every paragraph. Enter on a list item opens its detail card.
- **Clear.** A "Clear highlights" action in the panel removes the highlights from the page for this tab only. The marks stay saved. Reloading the page brings them back if the page is still scanned.
- **Changing pages.** When the page changes without a full load (single-page navigation), the highlights are removed at once and the panel goes back to Connected idle. A new scan starts only when the user presses "Scan this page", or the page matches an allowed site.
- **Page without a scan.** No highlight is drawn and the page shows nothing from kata.

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
- **Not colour alone.** Each mark has an icon and a text label (New, Known, Not tagged). Errors have a text message and an icon, not only a red border. Highlights on the page have a tag or dot, not only a tint.
- **Reduced motion.** Under `prefers-reduced-motion: reduce` the progress bar does not animate, the detail card fades without motion, and no element slides. Progress is still shown as a number.
- **Screen readers.** Status changes (scan progress, "Marked as known", errors) are announced in one polite live region. Errors that block an action use an assertive region once.
- **Text size and width.** The panel works at 200% text size and at a width of about 280 px without horizontal scrolling. Labels wrap; they are not cut.
- **Touch targets.** Buttons and list rows are at least 44 by 44 CSS px.

## 7. Themes

- Light and dark themes use the same tokens (`extension-ui/tokens.css`). The panel follows the browser's colour scheme by default.
- Both themes are checked against the contrast rule in section 6.

## 8. Open points for the owner

- Whether "Scan this page" should show a short confirmation the first time per site.
- Whether the review keys (1, 2, 3) should also be shown on the page detail card.
- Final wording of the three marks (New, Known, Not tagged).
