import type { ConceptMark } from "../../coreClientTypes";
import { button, el } from "../dom";
import { TEXT_EXAM_RESULT_PROPOSALS } from "../strings";

const [TITLE, NOTE, MOVE, KEEP, PICK_BY_HAND, DONE, NO_SCORES, FAILED] = TEXT_EXAM_RESULT_PROPOSALS;

/** One proposed concept to review after an exam, with its domain label. */
export interface ReviewProposal {
  conceptId: number;
  label: string;
  domain: string;
}

/** The choice of one proposal: move it to Learning or keep it Known. */
export type ProposalChoice = Extract<ConceptMark["state"], "learning" | "known">;

/** Props of the concepts-to-review screen. */
export interface ExamProposalsProps {
  proposals: ReviewProposal[];
  failed: boolean;
}

/** Actions of the concepts-to-review screen. Only onDone changes any mark. */
export interface ExamProposalsHandlers {
  onDone: (moves: { conceptId: number; state: ProposalChoice }[]) => void;
  onPickByHand: () => void;
}

/**
 * Concepts to review: one row per proposal with Move to Learning and Keep Known. Keep Known is the
 * default. Clicking a choice only changes the row; no mark is applied until Done, which sends the
 * whole list of choices once. With no domain scores the screen shows "No domain scores were
 * entered."; a failed load shows "Could not load the proposals.".
 */
export function renderExamProposals(props: ExamProposalsProps, handlers: ExamProposalsHandlers): HTMLElement {
  const screen = el("section", undefined, "exam-proposals");
  screen.append(el("h2", TITLE));
  if (props.failed) {
    screen.append(el("p", FAILED, "status error"));
  } else if (props.proposals.length === 0) {
    screen.append(el("p", NO_SCORES, "status"));
  } else {
    screen.append(el("p", NOTE, "note"));
    const choices = new Map<number, ProposalChoice>();
    for (const proposal of props.proposals) choices.set(proposal.conceptId, "known");
    const list = el("ul");
    for (const proposal of props.proposals) {
      const item = el("li", undefined, "proposal");
      const move = button(MOVE, () => choices.set(proposal.conceptId, "learning"), "move-to-learning");
      const keep = button(KEEP, () => choices.set(proposal.conceptId, "known"), "keep-known");
      item.append(el("span", proposal.label, "label"), el("span", proposal.domain, "domain"), move, keep);
      list.append(item);
    }
    screen.append(list);
    screen.append(button(DONE, () => handlers.onDone(collectMoves(props.proposals, choices)), "done"));
  }
  screen.append(button(PICK_BY_HAND, () => handlers.onPickByHand(), "pick-by-hand"));
  return screen;
}

/** The choices that move a concept to Learning, in proposal order. Keep Known rows are left out. */
function collectMoves(
  proposals: ReviewProposal[],
  choices: Map<number, ProposalChoice>,
): { conceptId: number; state: ProposalChoice }[] {
  return proposals
    .filter((p) => choices.get(p.conceptId) === "learning")
    .map((p) => ({ conceptId: p.conceptId, state: "learning" as const }));
}
