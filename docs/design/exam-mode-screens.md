# Exam mode: proposed screens and strings

Status: proposed

Decision D-J (`docs/decisions.md`, "Exam mode: D-J strings owner step"): phase 1 writes the proposed
screens and strings here. The owner approves them; a later task adds the approved strings to the
screen inventory and the string table. The mode is always "Exam mode", never bare "exam". No
provider brand names. Strings of the M25 course exam live in `extension/tests/fixtures/screen-inventory.json`
and are not repeated here.

| screen id | string key | proposed text | where it shows | note |
| --- | --- | --- | --- | --- |
| em-switch | `em-switch-label` | Exam mode | side panel, mode switch | label of the switch |
| em-switch | `em-switch-effect` | Answers on this page are recorded while on. | side panel, under the switch | says what the switch does |
| em-pin | `em-pin-menu` | Exam mode | floating pin menu | menu item that turns the mode on or off |
| em-pin | `em-pin-tooltip` | Exam mode is on: recording | floating pin, hover text | shown with the tiny dot on the pin |
| em-unreadable | `em-unreadable-text` | This question cannot be read. Exam mode skips it. | page, in place of the question panel | shown when the page text is not readable |
| em-result | `em-result-title` | Exam mode result | result screen, heading | heading after the mode ends |
| em-result | `em-result-topics` | Topics | result screen, section label | topics the owner picked by hand |
| em-result | `em-result-weak` | Suggestions | result screen, section label | weak points, labelled as suggestions, not facts |
| em-result | `em-result-score` | Score | result screen, field label | score field; no answer key is shown |
| em-result | `em-result-date` | Date | result screen, field label | date of the result |
| em-result | `em-result-passfail` | Pass or fail | result screen, field label | pass or fail field |
| em-result | `em-result-picked` | Picked by hand | result screen, topic list note | marks topics the owner picked by hand |
| em-proposals | `em-prop-confirm` | Confirm | proposals screen, button | confirms one proposal; creates no concept on its own |
| em-proposals | `em-prop-dismiss` | Dismiss | proposals screen, button | dismisses one proposal |
| em-proposals | `em-prop-needs-practice` | Needs practice | proposals screen, weak point label | decision 36 wording for the learning state |
| em-error | `em-error-core` | Kata core is not reachable. Exam mode is off. | error panel | shown when core cannot be reached |
| em-error | `em-error-idle` | Exam mode ended: the session was idle. | error panel, after idle timeout | shown when idle timeout ends the session |
