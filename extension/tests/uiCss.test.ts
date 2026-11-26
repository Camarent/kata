import { describe, expect, it } from "vitest";
import { PANEL_CSS } from "../src/ui/panelCss";
import { CARD_CSS } from "../src/ui/cardCss";

interface CssRule {
  selectors: string[];
  decls: Map<string, string>;
}

/** Flattens a stylesheet into rules; @media and @keyframes bodies are read as plain rules. */
function parseRules(css: string): CssRule[] {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: CssRule[] = [];
  for (const m of text.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = m[1].split(",").map((s) => s.trim()).filter((s) => s.length > 0);
    const decls = new Map<string, string>();
    for (const part of m[2].split(";")) {
      const colon = part.indexOf(":");
      if (colon < 0) continue;
      decls.set(part.slice(0, colon).trim(), part.slice(colon + 1).trim());
    }
    rules.push({ selectors, decls });
  }
  return rules;
}

const RULES = [...parseRules(PANEL_CSS), ...parseRules(CARD_CSS)];

/** Selectors that are controls: a rule naming one may not set a min size below 36px. */
const INTERACTIVE = /\.(btn|tab|chip-btn|connind|pinbtn|drag|x|choice|thead|rname|imgpin)(?![\w-])|(^|[\s>+~])(input|select|textarea)(?![\w-])/;

/** The compound a selector styles: `.thead .tn` styles `.tn`, `.rrow .rname` styles `.rname`. */
function lastCompound(selector: string): string {
  return selector.split(/[\s>+~]+/).pop() ?? "";
}

/** Properties that give a rule a size; a sized control rule must carry a 36px minimum itself. */
const SIZE_PROPS = ["width", "height", "min-width", "min-height"];

/** Bare control selectors that must carry a 36px minimum height and width. */
const REQUIRED_TARGETS = [".btn", ".tab", ".chip-btn", ".connind", ".pinbtn", ".drag", ".x", ".choice", ".thead", ".rrow .rname", ".imgpin"];

/** Class names of the approved prototype stylesheet, minus the dev bar, drawer and sample page. */
const PROTOTYPE_CLASSES = ("abar alert badge banner bar bicon block btn card card-item check chev chip-btn choice cloud cnt confirm connind count counts crow crow2 danger def dot down drag err field fig flash float full genblock hl ib ibgroup ibrow ico imgpin indent known l1 l2 learning ln mc mcs menu menu-list mixed modal modal-back muted name new nm note ok on open panel panel-body panel-head path pick pinbtn pincount pinwrap popover primary quizpin right rname row rows rrow rvbar rvsearch s-known s-learning s-new sec seg sel selwrap sg shell sico skip small sortrow space spinner sr st-known st-learning st-mixed st-new stack sub sync tab tabs tag tbar thead title tn tnode toast topic tree up warn wrong x").split(" ").filter((n) => n !== "shell");

/** Properties a hover rule may not change, because the layout would shift. */
const LAYOUT_PROPS = /^(width|height|min-width|min-height|max-width|max-height|margin(-[a-z]+)?|border|border-width|border-(top|right|bottom|left)(-width)?)$/;

/** Colour token pairs (text or icon colour, background) that must reach 4.5:1. */
const PAIRS: Array<[string, string]> = [
  ["color-text", "color-bg"],
  ["color-text", "color-surface"],
  ["color-text-muted", "color-bg"],
  ["color-text-muted", "color-surface"],
  ["color-accent-text", "color-accent"],
  ["color-text", "color-known-tint"],
  ["color-text", "color-new-tint"],
  ["color-text", "color-learning-tint"],
  ["color-known", "color-bg"],
  ["color-accent-text", "color-known"],
  ["color-known", "color-surface"],
  ["color-learning", "color-bg"],
  ["color-new", "color-bg"],
  ["color-error", "color-bg"],
  ["color-error", "color-error-bg"],
  ["color-warning", "color-bg"],
  ["color-warning", "color-warning-bg"],
  ["color-learning", "color-learning-tint"],
  ["color-accent", "color-bg"],
];

/** Colour values of the first rule with this exact selector list entry. */
function tokensOf(selector: string): Map<string, string> {
  const rule = RULES.find((r) => r.selectors.includes(selector));
  if (!rule) throw new Error(`no rule for ${selector}`);
  const out = new Map<string, string>();
  for (const [name, value] of rule.decls) {
    if (name.startsWith("--color-") && /^#[0-9a-fA-F]{6}$/.test(value)) out.set(name, value);
  }
  return out;
}

function channel(hex: string, at: number): number {
  const c = parseInt(hex.slice(at, at + 2), 16) / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  return 0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("panel and card stylesheets", () => {
  it("export the prototype class rules without the dev bar or sample page", () => {
    const css = PANEL_CSS + CARD_CSS;
    for (const name of PROTOTYPE_CLASSES) {
      expect(css, `.${name}`).toMatch(new RegExp(`\\.${name}(?![\\w-])`));
    }
    expect(css).not.toMatch(/\.dev\b|\.drawer|\.browser|#pageHost|\.stage\b/);
  });

  it("sets 36px minimum height and width on every interactive control", () => {
    for (const target of REQUIRED_TARGETS) {
      const rule = RULES.find((r) => r.selectors.includes(target));
      expect(rule, target).toBeDefined();
      expect(rule?.decls.get("min-height"), target).toBe("36px");
      expect(rule?.decls.get("min-width"), target).toBe("36px");
    }
    for (const rule of RULES) {
      if (!rule.selectors.some((s) => INTERACTIVE.test(lastCompound(s)))) continue;
      // A rule that sets no size (colour, hover or state rules) inherits the base size.
      if (!SIZE_PROPS.some((prop) => rule.decls.has(prop))) continue;
      for (const prop of ["min-height", "min-width"]) {
        const value = rule.decls.get(prop);
        expect(value, `${prop} missing in ${rule.selectors.join(", ")}`).toBeDefined();
        expect(value, `${prop} in ${rule.selectors.join(", ")}`).toMatch(/^(\d+)px$/);
        expect(parseInt(value, 10), `${prop} in ${rule.selectors.join(", ")}`).toBeGreaterThanOrEqual(36);
      }
    }
  });

  it("keeps hover rules free of size, margin and border-width changes", () => {
    for (const rule of RULES) {
      if (!rule.selectors.some((s) => s.includes(":hover"))) continue;
      for (const prop of rule.decls.keys()) {
        expect(prop, rule.selectors.join(", ")).not.toMatch(LAYOUT_PROPS);
      }
    }
  });

  it("reaches 4.5:1 for every text and background token pair in light and dark", () => {
    // The system-dark tokens sit in the prefers-color-scheme block, not in :root[data-theme="dark"].
    for (const theme of [":root", ':root:not([data-theme="light"])', ':root[data-theme="dark"]']) {
      const tokens = tokensOf(theme);
      for (const [fg, bg] of PAIRS) {
        const a = tokens.get(`--${fg}`);
        const b = tokens.get(`--${bg}`);
        expect(a, `${theme} --${fg}`).toBeDefined();
        expect(b, `${theme} --${bg}`).toBeDefined();
        expect(contrast(a ?? "", b ?? ""), `${theme} ${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });
});
