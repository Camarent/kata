import { el } from "./dom";

export interface ConfirmOptions {
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
}

/**
 * Inline confirm inside host: the message, a confirm button and a cancel button. Resolves true on
 * confirm and false on cancel, then removes its box from host.
 */
export function askConfirm(host: HTMLElement, options: ConfirmOptions): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    const box = el("div", undefined, "confirm");
    const message = el("span", options.message, "confirm-message");
    const confirm = el("button", options.confirmLabel, "confirm-yes");
    confirm.type = "button";
    const cancel = el("button", options.cancelLabel ?? "Cancel", "confirm-no");
    cancel.type = "button";
    const done = (ok: boolean): void => {
      box.remove();
      resolve(ok);
    };
    confirm.addEventListener("click", () => done(true));
    cancel.addEventListener("click", () => done(false));
    box.append(message, confirm, cancel);
    host.append(box);
  });
}
