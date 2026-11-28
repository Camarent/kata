import { CLASS_HL, highlightItem, type HighlightResult } from "./highlight";
import type { HlMenuOptions } from "./ui/overlay/hlMenu";
import { attachHlHover } from "./ui/overlay/hlMenu";
import { BLOCK_ATTR } from "./scanner";
import type { PanelMessage, PanelReply, RuntimeLike } from "./messages";
import type { ScanConceptItem } from "./coreClientTypes";

/** The page overlays on highlighted words: one hover menu per `.hl` word span. */
export interface OverlayHost {
  /** Attaches a hover menu to every `.hl` word of `doc`, replacing the menus attached before. */
  attach(doc: Document, results: HighlightResult[]): void;
  /** Removes every hover menu attached so far. */
  clear(): void;
}

/** Sends one panel message through the background; throws the background's error when it failed. */
async function sendPanel(runtime: RuntimeLike, message: PanelMessage): Promise<void> {
  const reply = (await runtime.sendMessage(message)) as PanelReply | undefined;
  if (reply?.ok !== true) throw new Error(reply?.ok === false ? reply.error : "no reply from background");
}

/** Menu options for one word: the concept actions go to the background as panel messages. */
function menuOptions(runtime: RuntimeLike, topicId: number, item: ScanConceptItem): HlMenuOptions {
  return {
    topicId,
    word: item.word,
    item,
    offline: false,
    client: {
      chooseConcept: (topic, word, conceptId) =>
        sendPanel(runtime, { type: "panel:chooseConcept", topicId: topic, word, conceptId }),
      reassignConcept: (topic, word, fromConceptId, toConceptId) =>
        sendPanel(runtime, { type: "panel:reassignConcept", topicId: topic, word, fromConceptId, toConceptId }),
    },
    onState: (state) => {
      // A word without a concept has no mark to set.
      if (item.conceptId === null) return;
      return sendPanel(runtime, { type: "panel:setConcept", conceptId: item.conceptId, state });
    },
  };
}

/** Creates the overlay host of one page; `runtime` carries the menu actions to the background. */
export function createOverlayHost(runtime: RuntimeLike): OverlayHost {
  let detaches: (() => void)[] = [];
  const clear = (): void => {
    for (const detach of detaches) detach();
    detaches = [];
  };
  return {
    clear,
    attach(doc, results) {
      clear();
      const topics = new Map<string, number>();
      for (const result of results) {
        if (result.topic !== null) topics.set(result.blockId, result.topic.id);
      }
      for (const span of Array.from(doc.querySelectorAll<HTMLElement>(`.${CLASS_HL}`))) {
        const item = highlightItem(span);
        const blockId = span.closest(`[${BLOCK_ATTR}]`)?.getAttribute(BLOCK_ATTR);
        const topicId = blockId === undefined || blockId === null ? undefined : topics.get(blockId);
        if (item === undefined || topicId === undefined) continue;
        detaches.push(attachHlHover(span, menuOptions(runtime, topicId, item)));
      }
    },
  };
}
