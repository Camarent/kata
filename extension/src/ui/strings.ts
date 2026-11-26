/** UI text of every inventory screen, verbatim from tests/fixtures/screen-inventory.json. One const per screen id: TEXT_<ID>, id upper-cased with - as _. */

export const TEXT_SIGNIN = [
  "Sign in to kata",
  "Server URL",
  "Code",
  "Device label",
  "Sign in",
  "Where do I get a code?",
  "Signing in...",
  "Could not sign in. Check the Server URL and the Code.",
  "Server not reachable.",
] as const;

export const TEXT_SIGNED_OUT = [
  "You are signed out.",
  "Sign in",
  "Scan, Review, Courses and Tracks need a signed-in device.",
] as const;

export const TEXT_CONN_DETAIL = [
  "Connected",
  "Server down, 3 not synced",
  "Server down",
  "Retry now",
  "Show unsynced marks",
  "Open settings",
  "Scan, Quiz and Generate course are off until the server answers.",
] as const;

export const TEXT_OFFLINE_QUEUE = [
  "Not synced marks",
  "Nothing waiting to sync.",
  "Not synced",
  "Synced",
  "Marks are kept in this browser and sent in order when the server answers.",
  "Your mark wins over a trainer update.",
  "Retry now",
  "Back",
] as const;

export const TEXT_PIN = [
  "kata",
  "Open card",
  "Collapse pin",
  "12 new",
  "Server down",
  "Focus mode is on.",
  "Undo",
  "Nothing to undo",
] as const;

export const TEXT_PIN_COLLAPSED = [
  "Open pin",
] as const;

export const TEXT_CARD_MAIN = [
  "New",
  "Learning",
  "Known",
  "Top gaps",
  "No scan yet. Scan this page to see concepts.",
  "Scan page",
  "Summary",
  "Quiz this page",
  "Focus mode",
  "Open panel",
  "Collapse card",
  "Server down. Scan and Quiz are off.",
  "Edits are made in the panel.",
] as const;

export const TEXT_CARD_SCAN = [
  "Scanning...",
  "Found 24 concepts: 12 New, 7 Learning, 5 Known.",
  "This page has no teaching content.",
  "Could not scan this page.",
  "Show in panel",
  "Scan again",
  "Back",
  "Focus mode is on. Results show only in the panel.",
  "Server down. Scan is off.",
] as const;

export const TEXT_CARD_SUMMARY = [
  "Knowledge summary",
  "Page text summary",
  "Topics found on this page",
  "Scan the page first.",
  "Writing the page text summary...",
  "Could not write the page text summary.",
  "Open in panel",
  "Back",
  "The page text summary is queued. Open the summary again in a moment.",
] as const;

export const TEXT_FOCUS_CONFIRM = [
  "Focus mode",
  "Ends after",
  "3 hours",
  "While on: no jokes, no pin nudges, no inline quiz offers, no page highlights, no inline mark buttons. Scan still works; results show only in the panel.",
  "Turn on",
  "Turn off",
  "Cancel",
  "Focus mode ends at 14:30.",
] as const;

export const TEXT_JOKE_CLOUD = [
  "Close joke",
] as const;

export const TEXT_HL_HOVER_MENU = [
  "New",
  "Known",
  "Learning",
  "Add to list",
  "Not this meaning",
  "No other meaning known",
  "Not synced",
  "In lists: Networking basics",
  "Also written: SYN-ACK",
  "Networking > TCP",
  "Delete",
  "Ignore from now on",
] as const;

export const TEXT_HL_WHICH_ONE = [
  "Which one?",
  "Window",
  "Networking > TCP",
  "Software > UI",
  "Word on the page: window",
] as const;

export const TEXT_BLOCK_MENU = [
  "All New",
  "All Known",
  "All Learning",
  "Add all to list",
  "Mixed",
  "Concepts in this block",
  "Not shown as a word in the text",
] as const;

export const TEXT_IMAGE_PIN_MENU = [
  "All New",
  "New",
  "This image is one block.",
  "Concepts in this image",
  "All Known",
  "All Learning",
  "Add all to list",
  "Known",
  "Learning",
  "Add to list",
  "Could not read this image.",
] as const;

export const TEXT_INLINE_QUIZ_PIN = [
  "Quiz this section",
  "5 questions",
] as const;

export const TEXT_LIST_PICKER = [
  "Add to list",
  "Pick a list",
  "You have no lists yet.",
  "New list",
  "Add",
  "Cancel",
  "Could not load your lists.",
  "Added to Networking basics.",
] as const;

export const TEXT_SCAN_RESULTS = [
  "Scan results",
  "Scan page",
  "Sort by",
  "Name",
  "Added date",
  "Last viewed",
  "Relevance",
  "A to Z",
  "Z to A",
  "Newest first",
  "Oldest first",
  "Most recent first",
  "Least recent first",
  "Most relevant first",
  "Least relevant first",
  "Known",
  "Learning",
  "New",
  "Add to list",
  "Add all concepts of topic",
  "Quiz this topic",
  "Knowledge summary",
  "Focus mode",
  "Review",
  "Courses",
  "Tracks",
  "Settings",
  "Scan a page to see its concepts.",
  "Scanning...",
  "Could not scan this page.",
  "Server down. Scan is off.",
  "Focus mode is on. Results show only here.",
] as const;

export const TEXT_SUMMARY_PANEL = [
  "Knowledge summary",
  "Page text summary",
  "Topics on this page",
  "Concepts per topic",
  "Scan the page first.",
  "Writing the page text summary...",
  "Could not write the page text summary.",
  "Back to scan results",
  "Add all concepts of topic",
] as const;

export const TEXT_REVIEW = [
  "Review",
  "Sort by",
  "Name",
  "Added date",
  "Last viewed",
  "Relevance",
  "A to Z",
  "Z to A",
  "Newest first",
  "Oldest first",
  "Most recent first",
  "Least recent first",
  "Most relevant first",
  "Least relevant first",
  "New",
  "Learning",
  "Known",
  "Quiz me",
  "Add to list",
  "No concepts yet. Scan a page first.",
  "Could not load concepts.",
  "Not synced",
  "Search concepts",
  "N of M concepts",
  "Only this page",
  "Collapse all",
  "Expand all",
  "Delete",
  "Ignore from now on",
  "Yes, delete",
  "Yes, ignore",
  "Cancel",
  "Delete? A later scan can bring it back as New.",
  "Ignore from now on? It is hidden and never found again.",
] as const;

export const TEXT_COURSES_TAB = [
  "Courses",
  "Lists",
  "Lists are drafts. A list becomes a course when you generate it.",
  "You have no courses yet.",
  "You have no lists yet.",
  "Open course",
  "Open list",
  "New list",
  "Generate course",
  "Sort by",
  "Name",
  "Added date",
  "Last viewed",
  "Relevance",
  "A to Z",
  "Z to A",
  "Newest first",
  "Oldest first",
  "Most recent first",
  "Least recent first",
  "Most relevant first",
  "Least relevant first",
  "Version 2",
  "Could not load courses.",
  "Server down. Generate course is off.",
  "Delete course",
  "Delete this course?",
  "Yes, delete",
  "Could not delete the course.",
] as const;

export const TEXT_LIST_DETAIL = [
  "List",
  "This list is a draft. It is not a course.",
  "Rename",
  "Delete list",
  "Remove",
  "Add all concepts of topic",
  "Generate course",
  "Back",
  "This list is empty. Add concepts from a scan.",
  "Could not load this list.",
] as const;

export const TEXT_LIST_EDIT = [
  "List name",
  "Save",
  "Cancel",
  "Could not save the list.",
  "A list with this name exists.",
] as const;

export const TEXT_LIST_DELETE = [
  "Delete this list?",
  "The concepts stay marked as they are. Courses made from this list stay.",
  "Delete list",
  "Cancel",
  "Could not delete the list.",
] as const;

export const TEXT_COURSE_GENERATE = [
  "Generate course",
  "New concepts are in the course.",
  "Known concepts are left out.",
  "Learning concepts start at: 3-7 days",
  "Add an exam",
  "The exam questions differ from the practice questions. Passing confirms a concept is learned.",
  "Generate",
  "Cancel",
  "Generating...",
  "Could not generate the course.",
  "Server down. Generate course is off.",
  "Give the course a title.",
] as const;

export const TEXT_COURSE_DETAIL = [
  "Course preview",
  "Learning concepts start at: 3-7 days",
  "Change start",
  "Open course page",
  "Regenerate",
  "Start exam",
  "Back",
  "Version 2",
  "Could not load the course.",
] as const;

export const TEXT_COURSE_REGENERATE = [
  "Regenerate course",
  "Regenerate replaces this course. The new course is version 2.",
  "Carried over",
  "Concept states are kept.",
  "New",
  "Concepts added by new sources.",
  "Learning concepts start at: 3-7 days",
  "Regenerate",
  "Cancel",
  "Could not regenerate the course.",
] as const;

export const TEXT_COURSE_PAGE = [
  "Course items",
  "Start exam",
  "Back to panel",
  "Could not load the course page.",
] as const;

export const TEXT_QUIZ_RUN = [
  "Question 1 of 5",
  "Next",
  "Finish",
  "Stop quiz",
  "Source:",
  "Tier 1",
  "General reference",
  "Could not write questions for this topic.",
  "Server down. Quiz is off.",
  "Writing questions...",
] as const;

export const TEXT_QUIZ_END = [
  "Mark as New",
  "Quiz result",
  "Right answers move New concepts to Learning.",
  "Mark as Known",
  "I know SYN",
  "Add to list",
  "Done",
  "Not synced",
] as const;

export const TEXT_EXAM_RUN = [
  "Exam",
  "Question 1 of 10",
  "Source: Tier 1",
  "Next",
  "Finish exam",
  "Leave exam",
  "Could not load the exam.",
  "Turn on focus mode for the exam.",
] as const;

export const TEXT_EXAM_RESULT = [
  "Exam result",
  "Known",
  "Needs practice",
  "Right answers confirm the concept as Known. Nothing is lowered.",
  "Open course items",
  "Done",
  "Could not load the result.",
] as const;

export const TEXT_TRACKS_TAB = [
  "Tracks",
  "You have no tracks yet.",
  "Open track",
  "New track",
  "Sort by",
  "Name",
  "Added date",
  "Last viewed",
  "Relevance",
  "A to Z",
  "Z to A",
  "Newest first",
  "Oldest first",
  "Most recent first",
  "Least recent first",
  "Most relevant first",
  "Least relevant first",
  "Progress",
  "Velocity",
  "Too slow for the deadline.",
  "Could not load tracks.",
] as const;

export const TEXT_TRACK_CREATE = [
  "New track",
  "Name",
  "Goal",
  "Deadline",
  "Time budget (optional)",
  "Create track",
  "Cancel",
  "Could not create the track.",
] as const;

export const TEXT_TRACK_DETAIL = [
  "Track",
  "Goal",
  "Deadline",
  "Progress",
  "Velocity",
  "Finish date: 3 weeks earlier than planned.",
  "Too slow for the deadline.",
  "Progress dropped because a new source added concepts.",
  "Sources",
  "Add source",
  "Create list from missing concepts",
  "Quiz this track",
  "Generate course",
  "Enter exam results",
  "Sort by",
  "Name",
  "Added date",
  "Last viewed",
  "Relevance",
  "A to Z",
  "Z to A",
  "Newest first",
  "Oldest first",
  "Most recent first",
  "Least recent first",
  "Most relevant first",
  "Least relevant first",
  "Back",
  "This track has no sources yet.",
  "Could not load the track.",
] as const;

export const TEXT_SOURCE_ADD = [
  "Add source",
  "Paste text",
  "Choose file",
  "Use current page",
  "Use a course",
  "Add source",
  "Cancel",
  "Reading the source...",
  "Could not read this source.",
  "Nothing here looks like teaching content.",
] as const;

export const TEXT_SOURCE_CONFIRM_TREE = [
  "Confirm new topics",
  "These concepts join the track at once. Progress may drop.",
  "Remove",
  "Add to track",
  "Cancel",
  "Could not read this source.",
] as const;

export const TEXT_EXAM_RESULT_ENTRY = [
  "Enter exam results",
  "Date",
  "Passed",
  "Not passed",
  "Score",
  "Domain scores (optional)",
  "Add domain score",
  "Save result",
  "Cancel",
  "Could not save the result.",
] as const;

export const TEXT_EXAM_RESULT_PROPOSALS = [
  "Concepts to review",
  "These concepts are in domains with a low score. Move a concept to Learning only if you agree.",
  "Move to Learning",
  "Keep Known",
  "Pick topics by hand",
  "Done",
  "No domain scores were entered.",
  "Could not load the proposals.",
] as const;

export const TEXT_SETTINGS_HOME = [
  "Settings",
  "Connection",
  "Auto-scan sites",
  "Jokes",
  "Appearance",
  "Allowed sources",
  "Ignored words and topics",
] as const;

export const TEXT_SETTINGS_CONNECTION = [
  "Connection",
  "Server URL",
  "Device label",
  "Connected",
  "Server down",
  "Sign out",
  "Back",
] as const;

export const TEXT_SIGNOUT_CONFIRM = [
  "Sign out of this device?",
  "3 marks are not synced. They are lost if you sign out now.",
  "Sign out",
  "Cancel",
  "Could not sign out.",
] as const;

export const TEXT_SETTINGS_SITES = [
  "Auto-scan sites",
  "These sites are scanned when you open them.",
  "Remove",
  "Back",
  "No sites yet.",
] as const;

export const TEXT_SETTINGS_JOKES = [
  "Jokes",
  "Show jokes",
  "At most once every",
  "2 hours",
  "Source",
  "Jokes never show during a quiz, while marking or in focus mode.",
  "Back",
] as const;

export const TEXT_SETTINGS_APPEARANCE = [
  "Appearance",
  "Theme",
  "Light",
  "Dark",
  "System",
  "Back",
] as const;

export const TEXT_SETTINGS_ALLOWLIST = [
  "Allowed sources",
  "Tier 1",
  "Tier 2",
  "General reference. Used for practice only, never for exams.",
  "Add domain",
  "Domains you add start in Tier 2.",
  "Make Tier 1",
  "Remove",
  "Free to read without an account only.",
  "Back",
] as const;

export const TEXT_IGNORED_LIST = [
  "Ignored words and topics",
  "Ignored words and topics are hidden from scans and highlights.",
  "Nothing is ignored.",
  "Restore",
  "Back",
  "Topic",
  "Word",
  "Restored.",
] as const;

export const TEXT_PAGE_CHANGED = [
  "Page changed",
  "Page changed, scanning...",
  "The page changed. New words are marked. Your marks stay as they are.",
  "Focus mode is on. New words show only in the panel.",
  "Server down. Scan is off.",
  "Show in panel",
  "Back",
] as const;

