#!/usr/bin/env node
// Baseline gate for the isolated JS audit tools. Runs one tool, normalises its findings, and fails
// only on a finding that is not listed in the tool's tracked baseline file (one entry per line).
// Usage: node extension/tools-js/baseline-gate.mjs madge|knip
// The tool's own exit code is ignored: both tools exit 1 when they find something; the baseline decides.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TOOLS_DIR = path.dirname(fileURLToPath(import.meta.url));
const EXTENSION_DIR = path.dirname(TOOLS_DIR);
const bin = (name) => path.join(TOOLS_DIR, "node_modules", ".bin", name);

/** Rotates a cycle so its smallest node comes first: one spelling per cycle. */
function normaliseCycle(nodes) {
  const start = nodes.indexOf(nodes.reduce((a, b) => (b < a ? b : a)));
  return [...nodes.slice(start), ...nodes.slice(0, start)].join(" > ");
}

const TOOLS = {
  madge: {
    baseline: "madge-baseline.txt",
    cmd: bin("madge"),
    // --basedir .. makes the paths "src/<file>.ts"; the config in this folder skips type-only imports.
    args: ["--basedir", "..", "--circular", "--extensions", "ts", "--json", "../src"],
    cwd: TOOLS_DIR,
    findings: (out) => JSON.parse(out).map(normaliseCycle),
  },
  knip: {
    baseline: "knip-baseline.txt",
    cmd: bin("knip"),
    // knip finds knip.json only from its working directory, which is extension/.
    args: ["--production", "--include", "files", "--reporter", "json"],
    cwd: EXTENSION_DIR,
    findings: (out) => JSON.parse(out).issues.map((issue) => issue.file),
  },
};

function readBaseline(file) {
  return readFileSync(file, "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "" && !line.startsWith("#"));
}

function runTool(tool) {
  const run = spawnSync(tool.cmd, tool.args, { cwd: tool.cwd, encoding: "utf8" });
  if (run.error) throw run.error;
  // knip writes its JSON report to stderr; madge writes it to stdout.
  const out = run.stdout.trim() !== "" ? run.stdout : run.stderr;
  return out;
}

function main() {
  const name = process.argv[2];
  const tool = TOOLS[name];
  if (!tool) {
    console.error(`baseline-gate: unknown tool "${name ?? ""}"; use one of: ${Object.keys(TOOLS).join(", ")}`);
    process.exit(2);
  }
  const baselinePath = path.join(TOOLS_DIR, tool.baseline);
  const baseline = new Set(readBaseline(baselinePath));
  const found = tool.findings(runTool(tool));
  const foundSet = new Set(found);
  const fresh = [...foundSet].filter((item) => !baseline.has(item));
  const stale = [...baseline].filter((item) => !foundSet.has(item));
  for (const item of stale) console.log(`${name}: baseline entry no longer found (remove it): ${item}`);
  if (fresh.length > 0) {
    for (const item of fresh) console.log(`${name}: NEW finding not in ${tool.baseline}: ${item}`);
    console.log(`${name}: ${fresh.length} new finding(s); ${found.length - fresh.length} in baseline`);
    process.exit(1);
  }
  console.log(`${name}: ${found.length} finding(s), all in ${tool.baseline}`);
}

main();
