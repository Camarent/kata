import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import * as strings from "../src/ui/strings";

/** `npm --prefix extension test` runs with the extension folder as cwd. */
const EXTENSION_DIR = process.cwd();
/** Copy of the approved screen inventory; the text of every screen is pinned here. */
const screens: { id: string; text: string[] }[] = JSON.parse(
  readFileSync(join(EXTENSION_DIR, "tests/fixtures/screen-inventory.json"), "utf-8"),
);
/** Every exported TEXT_ array of strings.ts, by name (keyed `*_TEXT` objects are checked below). */
const table: Record<string, readonly string[]> = Object.fromEntries(
  Object.entries(strings).filter(([name]) => name.startsWith("TEXT_")),
) as Record<string, readonly string[]>;
/** Const name of a screen id: `TEXT_` plus the id upper-cased with `-` as `_`. */
const constName = (id: string): string => `TEXT_${id.toUpperCase().replace(/-/g, "_")}`;
/** Every string of every const, flattened. */
const allStrings = Object.values(table).flat();

/**
 * Glossary draft 4, section 3: terms that must not appear in UI text, with the rule they break.
 * Only the rules a flat string check can decide are here. Not string-checkable, so not covered
 * by this test: "topic" as block state (D1), "Lists" as its own bottom tab (D10, the sub-label
 * "Lists" in TEXT_COURSES_TAB is allowed), "Two summary buttons" on the card (D52), and the
 * Tier 2 / general reference wording for exams (D46, the general-reference text is allowed
 * because it says "never for exams"). The "Exam" rule is covered for the mini quiz screens only.
 */
const BANNED: { pattern: RegExp; why: string }[] = [
  { pattern: /\bdue/i, why: "no due concept (D39)" },
  { pattern: /\bmissed\b/i, why: "no nagging, 'You missed this' (D39)" },
  { pattern: /\bladder/i, why: "kata does no scheduling (D48, D49)" },
  { pattern: /marks move/i, why: "nothing is lowered (D19, D36)" },
  { pattern: /\bFailed\b/, why: "use 'Needs practice' (D36)" },
  { pattern: /paperclip/i, why: "the mascot is a safety pin (D17)" },
  { pattern: /side panel/i, why: "say 'Panel' (one word for one thing)" },
  { pattern: /\bpaid\b|paywalled/i, why: "no paid sources (D46)" },
  { pattern: /make a course from these gaps/i, why: "replaced by 'Add to list' (D7)" },
  { pattern: /regenerate creates a new course|many courses/i, why: "regenerate replaces; version 2 (D35)" },
];

describe("ui strings pinned to the screen inventory", () => {
  it("exports one const per inventory screen id", () => {
    expect(screens).toHaveLength(48);
    expect(Object.keys(table)).toHaveLength(48);
    for (const screen of screens) {
      expect(table).toHaveProperty([constName(screen.id)]);
    }
  });

  it.each(screens.map((screen) => [screen.id, screen] as const))(
    "%s text equals the inventory text verbatim",
    (_id, screen) => {
      expect(table[constName(screen.id)]).toEqual(screen.text);
    },
  );

  it("every keyed panel string is an inventory string", () => {
    const inventory = new Set(screens.flatMap((screen) => screen.text));
    for (const [name, group] of Object.entries(strings).filter(([n]) => n.endsWith("_TEXT"))) {
      for (const [key, text] of Object.entries(group)) {
        expect(inventory.has(text as string), `${name}.${key}`).toBe(true);
      }
    }
  });

  it("named keys map to their inventory strings (review, block-menu, courses-tab)", () => {
    const review = screens.find((s) => s.id === "review")?.text ?? [];
    const reviewNamed: Record<keyof typeof strings.REVIEW_TEXT, string> = {
      new: "New",
      learning: "Learning",
      known: "Known",
      noConcepts: "No concepts yet. Scan a page first.",
      loadFailed: "Could not load concepts.",
      search: "Search concepts",
      count: "N of M concepts",
      onlyPage: "Only this page",
      collapseAll: "Collapse all",
      expandAll: "Expand all",
      delete: "Delete",
      ignore: "Ignore from now on",
      yesDelete: "Yes, delete",
      yesIgnore: "Yes, ignore",
      cancel: "Cancel",
      deleteNote: "Delete? A later scan can bring it back as New.",
      ignoreNote: "Ignore from now on? It is hidden and never found again.",
    };
    for (const [key, text] of Object.entries(reviewNamed)) {
      expect(strings.REVIEW_TEXT[key as keyof typeof reviewNamed], key).toBe(text);
      expect(review, key).toContain(text);
    }

    const courses = screens.find((s) => s.id === "courses-tab")?.text ?? [];
    const coursesNamed: Record<keyof typeof strings.COURSES_TAB_TEXT, string> = {
      courses: "Courses",
      noCourses: "You have no courses yet.",
      openCourse: "Open course",
      generate: "Generate course",
      loadFailed: "Could not load courses.",
      serverDown: "Server down. Generate course is off.",
      deleteCourse: "Delete course",
      deleteAsk: "Delete this course?",
      deleteYes: "Yes, delete",
      deleteFailed: "Could not delete the course.",
    };
    for (const [key, text] of Object.entries(coursesNamed)) {
      expect(strings.COURSES_TAB_TEXT[key as keyof typeof coursesNamed], key).toBe(text);
      expect(courses, key).toContain(text);
    }
  });

  it("named block-menu and pin keys map to their inventory strings", () => {
    const blockMenu = screens.find((s) => s.id === "block-menu")?.text ?? [];
    const blockNamed: Record<keyof typeof strings.BLOCK_MENU_TEXT, string> = {
      allNew: "All New",
      allKnown: "All Known",
      allLearning: "All Learning",
      addAll: "Add all to list",
      mixed: "Mixed",
      title: "Concepts in this block",
      notInText: "Not shown as a word in the text",
    };
    for (const [key, text] of Object.entries(blockNamed)) {
      expect(strings.BLOCK_MENU_TEXT[key as keyof typeof blockNamed], key).toBe(text);
      expect(blockMenu, key).toContain(text);
    }

    const pin = screens.find((s) => s.id === "pin")?.text ?? [];
    const pinNamed: Record<keyof typeof strings.PIN_TEXT, string> = {
      offline: "Server down",
      undo: "Undo",
    };
    for (const [key, text] of Object.entries(pinNamed)) {
      expect(strings.PIN_TEXT[key as keyof typeof pinNamed], key).toBe(text);
      expect(pin, key).toContain(text);
    }
  });

  it("panel keyed objects map each key to its exact text", () => {
    const ignoredNamed: Record<keyof typeof strings.IGNORED_LIST_TEXT, string> = {
      title: "Ignored words and topics",
      note: "Ignored words and topics are hidden from scans and highlights.",
      empty: "Nothing is ignored.",
      restore: "Restore",
      back: "Back",
      topic: "Topic",
      word: "Word",
      restored: "Restored.",
      restoreFailed: "Could not restore this word or topic.",
    };
    const courseDetailNamed: Record<keyof typeof strings.COURSE_DETAIL_TEXT, string> = {
      preview: "Course preview",
      startNote: "Learning concepts start at: 3-7 days",
      changeStart: "Change start",
      openPage: "Open course page",
      regenerate: "Regenerate",
      startExam: "Start exam",
      back: "Back",
      loadFailed: "Could not load the course.",
    };
    const courseGenerateNamed: Record<keyof typeof strings.COURSE_GENERATE_TEXT, string> = {
      serverDown: "Server down. Generate course is off.",
    };
    const courseRegenerateNamed: Record<keyof typeof strings.COURSE_REGENERATE_TEXT, string> = {
      heading: "Regenerate course",
      warning: "Regenerate replaces this course. The new course is version 2.",
      carried: "Carried over",
      carriedNote: "Concept states are kept.",
      new: "New",
      newNote: "Concepts added by new sources.",
      start: "Learning concepts start at: 3-7 days",
      submit: "Regenerate",
      cancel: "Cancel",
      failed: "Could not regenerate the course.",
    };
    const signinNamed: Record<keyof typeof strings.SIGNIN_TEXT, string> = {
      unreachable: "Server not reachable.",
    };
    const trackDetailNamed: Record<keyof typeof strings.TRACK_DETAIL_TEXT, string> = {
      title: "Track",
      goal: "Goal",
      deadline: "Deadline",
      progress: "Progress",
      velocity: "Velocity",
      finishEarly: "Finish date: 3 weeks earlier than planned.",
      tooSlow: "Too slow for the deadline.",
      dropReason: "Progress dropped because a new source added concepts.",
      sources: "Sources",
      addSource: "Add source",
      quiz: "Quiz this track",
      back: "Back",
      noSources: "This track has no sources yet.",
      loadFailed: "Could not load the track.",
    };
    const tracksTabNamed: Record<keyof typeof strings.TRACKS_TAB_TEXT, string> = {
      title: "Tracks",
      empty: "You have no tracks yet.",
      open: "Open track",
      newTrack: "New track",
      sortBy: "Sort by",
      nameSort: "Name",
      addedSort: "Added date",
      viewedSort: "Last viewed",
      relevanceSort: "Relevance",
      progress: "Progress",
      tooSlow: "Too slow for the deadline.",
      loadFailed: "Could not load tracks.",
    };
    const trackCreateNamed: Record<keyof typeof strings.TRACK_CREATE_TEXT, string> = {
      title: "New track",
      nameLabel: "Name",
      goalLabel: "Goal",
      deadlineLabel: "Deadline",
      budgetLabel: "Time budget (optional)",
      create: "Create track",
      cancel: "Cancel",
      failed: "Could not create the track.",
    };
    const listDeleteNamed: Record<keyof typeof strings.LIST_DELETE_TEXT, string> = {
      question: "Delete this list?",
      note: "The concepts stay marked as they are. Courses made from this list stay.",
      delete: "Delete list",
      cancel: "Cancel",
      error: "Could not delete the list.",
    };
    const named: [string, Record<string, string>, Record<string, string>][] = [
      ["IGNORED_LIST_TEXT", strings.IGNORED_LIST_TEXT, ignoredNamed],
      ["COURSE_DETAIL_TEXT", strings.COURSE_DETAIL_TEXT, courseDetailNamed],
      ["COURSE_GENERATE_TEXT", strings.COURSE_GENERATE_TEXT, courseGenerateNamed],
      ["COURSE_REGENERATE_TEXT", strings.COURSE_REGENERATE_TEXT, courseRegenerateNamed],
      ["SIGNIN_TEXT", strings.SIGNIN_TEXT, signinNamed],
      ["TRACK_DETAIL_TEXT", strings.TRACK_DETAIL_TEXT, trackDetailNamed],
      ["TRACKS_TAB_TEXT", strings.TRACKS_TAB_TEXT, tracksTabNamed],
      ["TRACK_CREATE_TEXT", strings.TRACK_CREATE_TEXT, trackCreateNamed],
      ["LIST_DELETE_TEXT", strings.LIST_DELETE_TEXT, listDeleteNamed],
    ];
    for (const [name, group, expected] of named) {
      expect(Object.keys(group).sort(), name).toEqual(Object.keys(expected).sort());
      for (const [key, text] of Object.entries(expected)) {
        expect(group[key], `${name}.${key}`).toBe(text);
      }
    }
  });

  it("uses 'Summary' alone only on the card button (D52)", () => {
    const alone = screens.filter((s) => s.text.includes("Summary")).map((s) => s.id);
    expect(alone).toEqual(["card-main"]);
    expect(table[constName("card-main")]).toContain("Summary");
  });

  it("has no glossary section 3 banned term in any string", () => {
    for (const { pattern, why } of BANNED) {
      const hits = allStrings.filter((text) => pattern.test(text));
      expect(hits, why).toEqual([]);
    }
  });

  it("keeps the word 'Exam' out of the mini quiz screens (D19, D35)", () => {
    for (const id of ["quiz-run", "inline-quiz-pin", "quiz-end"]) {
      const hits = table[constName(id)].filter((text) => /\bexam\b/i.test(text));
      expect(hits, id).toEqual([]);
    }
  });
});
