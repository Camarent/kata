import { describe, expect, it } from "vitest";
import { DEFAULT_MIN_CHARS, scanBlocks } from "../src/scanner";

const LONG = "This paragraph has plenty of readable words in it.";
const LONG2 = "The second section also carries enough words to pass.";

function docOf(html: string): Document {
  return new DOMParser().parseFromString(html, "text/html");
}

describe("scanBlocks", () => {
  it("gives one block per headed section", () => {
    const blocks = scanBlocks(docOf(`<h2>Alpha</h2><p>${LONG}</p><h2>Beta</h2><p>${LONG2}</p>`));
    expect(blocks).toHaveLength(2);
    expect(blocks[0].text.startsWith("Alpha")).toBe(true);
    expect(blocks[1].text.startsWith("Beta")).toBe(true);
    expect(blocks.map((b) => b.id)).toEqual(["b0", "b1"]);
  });

  it("excludes script text inside a paragraph", () => {
    const html = `<h2>Setup</h2><p>Visible words here ok<script>var secret = "hidden-token-value";</script> and more visible</p>`;
    const blocks = scanBlocks(docOf(html));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].text).toContain("Visible words here ok and more visible");
    expect(blocks[0].text).not.toContain("hidden-token-value");
  });

  it("drops a short block and keeps the stable index id of the rest", () => {
    const blocks = scanBlocks(docOf(`<h2>Tiny</h2><p>x</p><h2>Long one</h2><p>${LONG}</p>`));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].id).toBe("b1");
    expect(blocks[0].text.startsWith("Long one")).toBe(true);
  });

  it("splits a page without headings on paragraphs", () => {
    const blocks = scanBlocks(docOf(`<p>${LONG}</p><p>${LONG2}</p>`));
    expect(blocks.map((b) => b.text)).toEqual([LONG, LONG2]);
  });

  it("sets data-kata-block on each block element", () => {
    const doc = docOf(`<h2>Alpha</h2><p>${LONG}</p><h2>Beta</h2><p>${LONG2}</p>`);
    const blocks = scanBlocks(doc);
    expect(doc.querySelector('[data-kata-block="b0"]')).toBe(blocks[0].el);
    expect(doc.querySelectorAll("[data-kata-block]")).toHaveLength(blocks.length);
  });

  it("does not treat a heading inside nav as a block", () => {
    const html = `<nav><h2>Site menu</h2><ul><li>${LONG}</li></ul></nav><h2>Real</h2><p>${LONG2}</p>`;
    const doc = docOf(html);
    const blocks = scanBlocks(doc);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].text.startsWith("Real")).toBe(true);
    expect(doc.querySelectorAll("[data-kata-block]")).toHaveLength(1);
  });

  it("excludes hidden content", () => {
    const blocks = scanBlocks(docOf(`<h2>Open</h2><p>${LONG}</p><div hidden><p>${LONG2}</p></div>`));
    expect(blocks).toHaveLength(1);
    expect(blocks[0].text).not.toContain(LONG2);
  });

  it("truncates text at maxChars", () => {
    const blocks = scanBlocks(docOf(`<p>${LONG}</p>`), { maxChars: 10 });
    expect(blocks[0].text).toBe(LONG.slice(0, 10));
  });

  it("uses the named default for minChars", () => {
    const short = "x".repeat(DEFAULT_MIN_CHARS - 1);
    const exact = "y".repeat(DEFAULT_MIN_CHARS);
    const blocks = scanBlocks(docOf(`<p>${short}</p><p>${exact}</p>`));
    expect(blocks.map((b) => b.text)).toEqual([exact]);
  });
});
