import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { beforeAll, describe, expect, it } from "vitest";

/** `npm --prefix extension test` runs with the extension folder as cwd. */
const EXTENSION_DIR = process.cwd();
/** The build runs tsc and esbuild; allow it a generous window on a cold cache. */
const BUILD_TIMEOUT_MS = 120_000;

/** True when a top-level statement is an import, an export, or carries an export modifier. */
function isModuleSyntax(statement: ts.Statement): boolean {
  if (ts.isImportDeclaration(statement)) return true;
  if (ts.isExportDeclaration(statement) || ts.isExportAssignment(statement)) return true;
  const modifiers = ts.canHaveModifiers(statement) ? ts.getModifiers(statement) : undefined;
  return modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword) ?? false;
}

describe("built content script", () => {
  beforeAll(() => {
    execSync("npm run build", { cwd: EXTENSION_DIR, stdio: "pipe" });
  }, BUILD_TIMEOUT_MS);

  it("dist/content.js is a classic script: no top-level import or export", () => {
    const source = readFileSync(join(EXTENSION_DIR, "dist", "content.js"), "utf8");
    const file = ts.createSourceFile("content.js", source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.JS);
    const offending = file.statements.filter(isModuleSyntax).map((statement) => statement.getText(file));
    expect(offending).toEqual([]);
  });
});
