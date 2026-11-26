/**
 * Design tokens and panel styles. Ported from the approved prototype stylesheet: the dev bar,
 * the sample page and the demo stage are left out. Every interactive control is at least
 * 36px tall and wide (touch target); hover rules change no size, margin or border width.
 */

/** Colour, spacing and type tokens: light by default, dark by system preference or data-theme. */
export const TOKENS_CSS = `
:root {
  color-scheme: light dark;
  --color-bg: #ffffff; --color-surface: #f5f6f8; --color-text: #1b1f24; --color-text-muted: #56606b;
  --color-border: #c9ced6; --color-accent: #1f5fbf; --color-accent-text: #ffffff; --color-focus: #0a5cd6;
  --color-known: #1d7a3c; --color-new: #56606b; --color-learning: #7d5f00;
  --color-known-tint: #d7f0df; --color-new-tint: #e4e7ec; --color-learning-tint: #fdf1b8;
  --color-error: #b3261e; --color-error-bg: #fdecea; --color-warning: #8a5a00; --color-warning-bg: #fff4e0;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --radius: 6px;
  --touch-min: 36px; --font-body: system-ui, sans-serif; --font-size: 15px; --font-size-small: 13px;
  --duration: 150ms; --shadow: 0 6px 20px rgba(0,0,0,.18);
  --gap: var(--space-2); --gap-lg: var(--space-3); --icon: 20px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --color-bg: #15181c; --color-surface: #1f242b; --color-text: #e6e9ee; --color-text-muted: #a4adb8;
    --color-border: #3a424d; --color-accent: #7fb0ff; --color-accent-text: #0b1220; --color-focus: #9cc3ff;
    --color-known: #6fd38f; --color-new: #a4adb8; --color-learning: #f0d466;
    --color-known-tint: #1d3a28; --color-new-tint: #2a3038; --color-learning-tint: #4a3f12;
    --color-error: #ff8a80; --color-error-bg: #3a1716; --color-warning: #ffcc80; --color-warning-bg: #3a2a10;
    --shadow: 0 6px 20px rgba(0,0,0,.6);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --color-bg: #15181c; --color-surface: #1f242b; --color-text: #e6e9ee; --color-text-muted: #a4adb8;
  --color-border: #3a424d; --color-accent: #7fb0ff; --color-accent-text: #0b1220; --color-focus: #9cc3ff;
  --color-known: #6fd38f; --color-new: #a4adb8; --color-learning: #f0d466;
  --color-known-tint: #1d3a28; --color-new-tint: #2a3038; --color-learning-tint: #4a3f12;
  --color-error: #ff8a80; --color-error-bg: #3a1716; --color-warning: #ffcc80; --color-warning-bg: #3a2a10;
  --shadow: 0 6px 20px rgba(0,0,0,.6);
}
:root[data-theme="light"] { color-scheme: light; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0ms !important; transition-duration: 0ms !important; }
}
`;

/** Base, buttons, fields, panel shell, tree, rows, review bars and full-width pages. */
const PANEL_RULES_CSS = `
* { box-sizing: border-box; }
body { margin: 0; background: var(--color-surface); color: var(--color-text); font-family: var(--font-body); font-size: var(--font-size); line-height: 1.45; }
h1, h2, h3, h4 { margin: 0 0 var(--space-2); line-height: 1.25; }
h2 { font-size: 18px; }
h3 { font-size: 15px; }
h4 { font-size: 13px; color: var(--color-text-muted); }
p { margin: 0 0 var(--space-2); }
a { color: var(--color-accent); }
:focus-visible { outline: 3px solid var(--color-focus); outline-offset: 2px; }
.muted { color: var(--color-text-muted); font-size: var(--font-size-small); }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.skip { position: absolute; left: -999px; top: 0; z-index: 200; background: var(--color-bg); color: var(--color-text); padding: 6px 10px; }
.skip:focus { left: 8px; top: 8px; }
.row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
.row.space { justify-content: space-between; }
.row.sec { margin-top: var(--gap-lg); }
.stack > * + * { margin-top: var(--space-2); }

.btn, .tab, .chip-btn {
  font: inherit; color: var(--color-text); background: var(--color-bg); border: 1px solid var(--color-border);
  border-radius: var(--radius); padding: 6px 12px; min-height: 36px; min-width: 36px; cursor: pointer;
}
.btn.small { min-height: 36px; min-width: 36px; padding: 2px 8px; font-size: var(--font-size-small); }
.btn:hover, .tab:hover { background: var(--color-surface); }
.btn.primary { background: var(--color-accent); color: var(--color-accent-text); border-color: var(--color-accent); }
.btn.primary:hover { filter: brightness(1.08); }
.btn.danger { color: var(--color-error); border-color: var(--color-error); }
.btn[aria-pressed="true"], .btn.on { background: var(--color-accent); color: var(--color-accent-text); border-color: var(--color-accent); }
.btn.s-known[aria-pressed="true"] { background: var(--color-known); border-color: var(--color-known); color: var(--color-accent-text); }
.btn.s-learning[aria-pressed="true"] { background: var(--color-learning-tint); color: var(--color-text); border-color: var(--color-learning); }
.btn.s-new[aria-pressed="true"] { background: var(--color-new-tint); color: var(--color-text); border-color: var(--color-new); }
.btn:disabled, select:disabled, input:disabled { opacity: .5; cursor: not-allowed; }
.btn.ib { display: inline-flex; align-items: center; justify-content: center; min-width: 36px; min-height: 36px; padding: 0; }
.btn.ib.s-known { color: var(--color-known); }
.btn.ib.s-learning { color: var(--color-learning); }
.btn.ib.s-new { color: var(--color-new); }
.btn.ib[aria-pressed="true"] { background: var(--color-surface); border-color: currentColor; box-shadow: inset 0 0 0 1px currentColor; }
.btn.ib.s-known[aria-pressed="true"] { background: var(--color-known-tint); }
.btn.ib.s-learning[aria-pressed="true"] { background: var(--color-learning-tint); }
.btn.ib.s-new[aria-pressed="true"] { background: var(--color-new-tint); }
.btn.ib.st-known { color: var(--color-known); }
.btn.ib.st-learning { color: var(--color-learning); }
.btn.ib.st-new { color: var(--color-new); }
.btn.ib.st-mixed { color: var(--color-accent); }
.ibgroup, .ibrow { display: inline-flex; align-items: center; gap: var(--space-1); flex-wrap: wrap; }

label { display: block; font-size: var(--font-size-small); color: var(--color-text-muted); margin: 0 0 var(--space-1); }
input[type=text], input[type=number], input[type=date], input[type=password], textarea, select {
  font: inherit; color: var(--color-text); background: var(--color-bg); border: 1px solid var(--color-border);
  border-radius: var(--radius); padding: 6px 8px; min-height: 36px; min-width: 36px; width: 100%;
}
select { width: auto; min-height: 36px; min-width: 36px; }
.selwrap { display: inline-flex; align-items: center; gap: var(--gap); margin: 0; color: var(--color-text); font-size: var(--font-size-small); }
.selwrap select { margin: 0; min-height: 36px; min-width: 36px; }
.check { min-height: 36px; margin: 0; display: flex; align-items: center; gap: var(--space-2); color: var(--color-text); font-size: var(--font-size); }
.check input { width: 18px; height: 18px; min-height: 36px; min-width: 36px; }
.field { margin: 0 0 var(--gap-lg); }

.ico { width: var(--icon); height: var(--icon); display: block; flex: none; }
.sg { display: inline-flex; vertical-align: middle; }
.sg .ico { width: 16px; height: 16px; }
.sg.known { color: var(--color-known); }
.sg.learning { color: var(--color-learning); }
.sg.new { color: var(--color-new); }
.def { margin: 0; font-size: var(--font-size-small); color: var(--color-text-muted); }
.path { color: var(--color-text-muted); font-size: var(--font-size-small); }
.note { font-size: var(--font-size-small); color: var(--color-text-muted); }
.tag { font-size: 12px; border: 1px solid var(--color-border); border-radius: 4px; padding: 0 6px; background: var(--color-surface); }

.panel { display: flex; flex-direction: column; width: 360px; max-width: 100%; min-height: 520px; max-height: 100vh; overflow: hidden; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 8px; box-shadow: var(--shadow); }
.panel-head { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-border); background: var(--color-surface); flex-wrap: wrap; }
.panel-head .title { flex: 1; font-weight: 600; display: flex; align-items: center; gap: 6px; }
.connind { font: inherit; font-size: 12px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 12px; padding: 2px 8px; min-height: 36px; min-width: 36px; cursor: pointer; color: var(--color-text); display: inline-flex; align-items: center; gap: 4px; }
.tabs { display: flex; border-bottom: 1px solid var(--color-border); }
.tabs .tab { flex: 1; border: 0; border-radius: 0; border-bottom: 3px solid transparent; background: none; padding: 8px 4px; font-size: 13px; }
.tabs .tab[aria-pressed="true"], .tabs .tab[aria-selected="true"] { background: none; color: var(--color-text); border-bottom-color: var(--color-accent); font-weight: 600; }
.panel-body { padding: var(--space-3); overflow: auto; flex: 1; }
.banner { border-radius: var(--radius); padding: 8px 10px; font-size: 13px; margin-bottom: var(--space-3); border: 1px solid var(--color-border); background: var(--color-surface); }
.banner.warn { background: var(--color-warning-bg); color: var(--color-warning); border-color: var(--color-warning); }
.banner.err { background: var(--color-error-bg); color: var(--color-error); border-color: var(--color-error); }
.banner.ok { background: var(--color-known-tint); border-color: var(--color-known); }
.spinner { width: 22px; height: 22px; border: 3px solid var(--color-border); border-top-color: var(--color-accent); border-radius: 50%; animation: spin 0.9s linear infinite; display: inline-block; vertical-align: middle; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }

.tree { display: flex; flex-direction: column; gap: var(--space-1); }
.tnode { margin: 0; }
.thead { display: flex; align-items: center; gap: var(--gap); width: 100%; text-align: left; min-height: 36px; min-width: 36px; padding: 0 var(--gap); background: var(--color-surface); border-color: transparent; font-weight: 600; }
.thead.topic { font-weight: 500; background: transparent; border-color: var(--color-surface); }
.thead .tn { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.thead .cnt { font-weight: 400; color: var(--color-text-muted); font-size: var(--font-size-small); }
.thead .chev { display: inline-flex; transition: transform var(--duration); }
.thead[aria-expanded="true"] .chev { transform: rotate(90deg); }
.thead[aria-expanded] { color: var(--color-text); }
.tree .indent { padding-left: var(--gap-lg); display: flex; flex-direction: column; gap: var(--space-1); }
.mcs { display: inline-flex; gap: var(--gap); font-weight: 400; font-size: 12px; }
.mc { display: inline-flex; align-items: center; gap: 2px; }
.mc .ico { width: 14px; height: 14px; }
.mc.known { color: var(--color-known); }
.mc.learning { color: var(--color-learning); }
.mc.new { color: var(--color-new); }
.tbar { display: flex; flex-wrap: wrap; gap: var(--gap); align-items: center; padding: var(--space-1) 0; }
.crow { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 5px 0; border-top: 1px solid var(--color-surface); }
.crow .name { flex: 1; min-width: 100px; }
.crow.sel { background: var(--color-surface); }
.crow2 { display: flex; flex-direction: column; gap: var(--space-1); padding: var(--space-1) 0; border-top: 1px solid var(--color-surface); }
.crow2 .l1 { display: flex; align-items: baseline; gap: var(--gap); min-width: 0; white-space: nowrap; }
.crow2 .nm { font-weight: 600; flex: none; max-width: 60%; overflow: hidden; text-overflow: ellipsis; }
.crow2 .path { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.crow2 .l2 { display: flex; align-items: center; gap: var(--gap); }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.rows .crow { margin: 0; }
.rrow { display: flex; }
.rrow .rname { flex: 1; display: flex; align-items: center; gap: var(--gap); text-align: left; border-color: transparent; background: transparent; min-height: 36px; min-width: 36px; padding: 0 var(--gap); }
.rrow .rname .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rrow.sel .rname { background: var(--color-surface); border-color: var(--color-border); }
.rrow .rname[aria-pressed="true"] { color: var(--color-text); background: var(--color-surface); border-color: var(--color-border); }
.seg { display: inline-flex; gap: 2px; }
.clamp2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.card-item { border: 1px solid var(--color-border); border-radius: var(--radius); padding: var(--space-2) var(--space-3); margin-bottom: var(--space-2); }
.card-item.flash { border-color: var(--color-accent); box-shadow: 0 0 0 2px var(--color-accent); }
.bar { height: 8px; border-radius: 4px; background: var(--color-surface); border: 1px solid var(--color-border); overflow: hidden; min-width: 80px; }
.bar > i { display: block; height: 100%; background: var(--color-known); }
.sortrow { display: flex; gap: var(--gap); margin: 0 0 var(--gap); align-items: center; flex-wrap: wrap; }
.sortrow .note { margin: 0; }
.choice { display: block; width: 100%; min-height: 36px; min-width: 36px; text-align: left; margin-bottom: 6px; }
.choice.right { border-color: var(--color-known); background: var(--color-known-tint); }
.choice.wrong { border-color: var(--color-error); background: var(--color-error-bg); }
.abar { display: flex; flex-direction: column; gap: var(--gap); padding: var(--gap); margin: 0 0 var(--space-1); background: var(--color-surface); border-radius: var(--radius); }
.abar > * { margin: 0; }
.confirm { display: flex; align-items: center; flex-wrap: wrap; gap: var(--gap); padding: var(--gap); border: 1px solid var(--color-error); border-radius: var(--radius); background: var(--color-error-bg); }
.rvbar { display: flex; flex-direction: column; gap: var(--gap); margin: 0 0 var(--gap-lg); }
.rvsearch { position: relative; }
.rvsearch input { padding-left: 34px; }
.rvsearch .sico { position: absolute; left: 8px; top: 50%; transform: translateY(-50%); pointer-events: none; color: var(--color-text-muted); }
.genblock { margin-bottom: var(--space-3); }
.genblock p { margin: 2px 0 0; }

.full { padding: var(--space-4) var(--space-4) 60px; max-width: 700px; margin: 0 auto; }
.full .menu-list { display: grid; gap: var(--space-2); }
.full .menu-list .btn { text-align: left; min-height: 36px; min-width: 36px; }
.sec { border-top: 1px solid var(--color-border); padding-top: var(--space-3); margin-top: var(--space-3); }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--color-surface); vertical-align: middle; }
`;

/** Panel styles: tokens followed by the panel rules. */
export const PANEL_CSS = TOKENS_CSS + PANEL_RULES_CSS;
