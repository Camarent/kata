/**
 * Floating card, pin, menus, popovers, toast and page overlay styles. Ported from the approved
 * prototype stylesheet; the dev bar and the sample page shell are left out. Tokens come from
 * panelCss so both stylesheets read the same colours. Every interactive control is at least
 * 36px tall and wide; hover rules change no size, margin or border width.
 */
import { TOKENS_CSS } from "./panelCss";

const CARD_RULES_CSS = `
.float { position: absolute; z-index: 20; right: 20px; bottom: 20px; display: flex; flex-direction: column; align-items: flex-end; gap: var(--space-2); font-family: var(--font-body); font-size: var(--font-size); line-height: 1.4; }
.pinwrap { display: flex; align-items: center; gap: var(--space-2); background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 28px; padding: 4px 10px 4px 4px; box-shadow: var(--shadow); }
.pinbtn { min-height: 36px; min-width: 36px; background: none; border: 0; padding: 2px; border-radius: 50%; cursor: pointer; color: var(--color-text); display: flex; }
.pinbtn svg { width: 36px; height: 36px; }
.pinbtn.alert svg { animation: wiggle 1.6s ease-in-out infinite; }
@keyframes wiggle { 0%,100% { transform: rotate(0); } 20% { transform: rotate(-12deg); } 40% { transform: rotate(10deg); } 60% { transform: rotate(-6deg); } }
.drag { min-height: 36px; min-width: 36px; cursor: grab; touch-action: none; color: var(--color-text-muted); background: none; border: 0; padding: 4px; font-size: 14px; }
.pincount { font-size: 13px; font-weight: 600; }
.card { width: 300px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 10px; box-shadow: var(--shadow); padding: var(--space-3); }
.card header { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
.card header h2 { flex: 1; margin: 0; font-size: 16px; }
.x { min-height: 36px; min-width: 36px; padding: 0 8px; background: none; border: 0; color: var(--color-text-muted); cursor: pointer; font: inherit; }
.counts { display: flex; gap: var(--space-2); margin: var(--space-2) 0; }
.count { flex: 1; text-align: center; border-radius: var(--radius); padding: 6px 2px; border: 1px solid var(--color-border); font-size: 12px; }
.count b { display: block; font-size: 20px; }
.count.new { background: var(--color-new-tint); }
.count.learning { background: var(--color-learning-tint); }
.count.known { background: var(--color-known-tint); }
.cloud { position: relative; max-width: 260px; background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 14px; padding: 10px 34px 10px 12px; box-shadow: var(--shadow); font-size: 14px; }
.cloud::after { content: ""; position: absolute; bottom: -8px; right: 30px; width: 14px; height: 14px; background: var(--color-bg); border-right: 1px solid var(--color-border); border-bottom: 1px solid var(--color-border); transform: rotate(45deg); }
.cloud .x { position: absolute; top: 4px; right: 4px; min-height: 36px; min-width: 36px; padding: 0 6px; }

.menu { position: absolute; z-index: 40; display: flex; flex-direction: column; gap: var(--gap); background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 8px; box-shadow: var(--shadow); padding: var(--space-2); font-family: var(--font-body); font-size: 14px; line-height: 1.4; min-width: 200px; max-width: 300px; }
.menu > *, .menu .row, .menu h3, .menu h4, .menu p { margin: 0; }
.menu .sub { display: block; margin: 0; font-size: 12px; font-weight: 400; color: var(--color-text-muted); }
.menu .btn.pick { display: flex; flex-direction: column; align-items: flex-start; text-align: left; min-width: 160px; min-height: 36px; }
.menu h3 { font-size: 14px; }
.menu ul { list-style: none; margin: 0; padding: 0; }
.menu li { display: flex; align-items: center; gap: var(--gap); flex-wrap: wrap; padding: var(--space-1) 0; border-top: 1px solid var(--color-surface); }
.menu li .name { flex: 1; min-width: 80px; }
.popover { position: fixed; z-index: 60; display: flex; flex-direction: column; gap: var(--gap); width: min(260px, calc(100% - 16px)); background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 8px; box-shadow: var(--shadow); padding: var(--gap-lg); font-size: 14px; }
.popover[hidden] { display: none; }
.popover > *, .popover .row, .popover p { margin: 0; }
.popover h2 { font-size: 15px; margin: 0; }
.modal-back { position: fixed; inset: 0; z-index: 60; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; padding: var(--space-4); }
.modal { width: min(360px, 100%); background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 10px; box-shadow: var(--shadow); padding: var(--space-4); }
.toast { position: fixed; left: 50%; bottom: 20px; transform: translateX(-50%); z-index: 90; display: flex; align-items: center; gap: var(--gap); background: #20242b; color: #ffffff; border-radius: 20px; padding: 8px 16px; font-size: 14px; }
.toast[hidden] { display: none; }
.toast .btn { color: #ffffff; background: transparent; border-color: #ffffff66; min-height: 36px; min-width: 36px; }
.toast .btn.ib { min-width: 36px; min-height: 36px; }

.block { position: relative; border: 2px solid transparent; border-radius: 6px; padding: 2px 44px 2px 6px; margin: 4px -8px; }
.block:hover, .block:focus-within { outline: 2px solid var(--color-border); outline-offset: -2px; }
.block[data-bstate="known"]:hover, .block[data-bstate="known"]:focus-within { outline-color: var(--color-known); }
.block[data-bstate="learning"]:hover, .block[data-bstate="learning"]:focus-within { outline-color: var(--color-learning); outline-style: dashed; }
.block[data-bstate="new"]:hover, .block[data-bstate="new"]:focus-within { outline-color: var(--color-new); outline-style: dotted; }
.block[data-bstate="mixed"]:hover, .block[data-bstate="mixed"]:focus-within { outline-style: dashed; outline-color: var(--color-accent); }
.block .bicon { position: absolute; top: 4px; right: 4px; width: 36px; display: flex; justify-content: center; visibility: hidden; font-family: var(--font-body); }
.block:hover .bicon, .block:focus-within .bicon, .bicon.open { visibility: visible; }
.badge { display: inline-block; font-family: var(--font-body); font-size: 12px; border-radius: 10px; padding: 1px 8px; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-text); white-space: nowrap; }
.badge.known { background: var(--color-known-tint); border-color: var(--color-known); }
.badge.learning { background: var(--color-learning-tint); border-color: var(--color-learning); }
.badge.new { background: var(--color-new-tint); border-color: var(--color-new); }
.badge.mixed { border-style: dashed; border-color: var(--color-accent); }
.imgpin { position: absolute; top: 4px; right: 4px; min-height: 36px; min-width: 36px; visibility: hidden; }
.fig { position: relative; }
.fig:hover .imgpin, .fig:focus-within .imgpin { visibility: visible; }
.fig svg { display: block; width: 100%; max-width: 560px; height: auto; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface); }
.fig svg text { fill: var(--color-text); font-family: var(--font-body); paint-order: stroke; stroke: var(--color-surface); stroke-width: 4px; stroke-linejoin: round; }
.fig svg .ln { stroke: var(--color-text); }
.quizpin { margin: 10px 0; font-family: var(--font-body); }
.hl { border-radius: 3px; padding: 0 2px; cursor: pointer; border-bottom: 2px solid transparent; }
.hl[data-state="known"] { background: var(--color-known-tint); border-bottom-color: var(--color-known); }
.hl[data-state="learning"] { background: var(--color-learning-tint); border-bottom-color: var(--color-learning); border-bottom-style: dashed; }
.hl[data-state="new"] { background: var(--color-new-tint); border-bottom-color: var(--color-new); border-bottom-style: dotted; }
.hl[data-state="ambiguous"] { border-bottom-color: var(--color-text-muted); border-bottom-style: dashed; }
.hl[data-state="ambiguous"]::after { content: "?"; font-size: 0.75em; vertical-align: super; margin-left: 1px; color: var(--color-text-muted); }
.hl.sync { position: relative; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--color-warning); vertical-align: middle; margin-left: 3px; }
.dot.up { background: var(--color-known); }
.dot.down { background: var(--color-error); }
`;

/** Card and page overlay styles: the shared tokens followed by the overlay rules. */
export const CARD_CSS = TOKENS_CSS + CARD_RULES_CSS;
