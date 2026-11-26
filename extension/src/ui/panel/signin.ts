import type { PanelHandlers } from "../../sidepanel";
import { CoreOfflineError, CoreTimeoutError } from "../../coreClient";
import { el } from "../dom";
import { TEXT_SIGNED_OUT, TEXT_SIGNIN } from "../strings";

const [HEADING, SERVER_LABEL, CODE_LABEL, DEVICE_LABEL, SUBMIT, , SIGNING_IN, FAILED, UNREACHABLE] = TEXT_SIGNIN;
const [SIGNED_OUT, SIGN_IN_BUTTON, NEEDS_DEVICE] = TEXT_SIGNED_OUT;

/** Props of the sign-in screen: the URL to prefill and whether Cancel shows (change server). */
export interface SignInScreenProps {
  prefill: string;
  canCancel: boolean;
}

/** Props of the signed-out screen: the URL the sign-in form opens with. */
export interface SignedOutScreenProps {
  prefill: string;
}

/**
 * Sign-in form: server URL, pairing code and device label. While onSignIn runs the form shows
 * "Signing in..." and the submit is disabled. A rejected sign-in shows "Server not reachable." when
 * the core is offline or times out, else the could-not-sign-in text.
 */
export function renderSignIn(handlers: PanelHandlers, props: SignInScreenProps): HTMLElement {
  const form = el("form", undefined, "signin");
  form.append(el("h2", HEADING));
  const serverLabel = el("label", SERVER_LABEL);
  const server = el("input");
  server.name = "baseUrl";
  server.type = "text";
  server.placeholder = "https://kata.example.org";
  server.value = props.prefill;
  serverLabel.append(server);
  const codeLabel = el("label", CODE_LABEL);
  const code = el("input");
  code.name = "code";
  code.type = "text";
  codeLabel.append(code);
  const deviceLabel = el("label", DEVICE_LABEL);
  const device = el("input");
  device.name = "deviceLabel";
  device.type = "text";
  deviceLabel.append(device);
  const submit = el("button", SUBMIT, "btn");
  submit.type = "submit";
  const error = el("p", undefined, "error");
  error.setAttribute("role", "alert");
  form.append(serverLabel, codeLabel, deviceLabel, submit);
  if (props.canCancel) {
    const cancel = el("button", "Cancel", "btn");
    cancel.type = "button";
    cancel.addEventListener("click", () => handlers.onCancelChange());
    form.append(cancel);
  }
  form.append(error);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = { baseUrl: server.value.trim(), code: code.value.trim(), deviceLabel: device.value.trim() };
    if (input.code === "" || input.deviceLabel === "") {
      error.textContent = "Enter the code and a device label";
      return;
    }
    if (input.baseUrl === "") {
      error.textContent = "Enter the server URL";
      return;
    }
    error.textContent = SIGNING_IN;
    submit.disabled = true;
    try {
      await handlers.onSignIn(input);
      error.textContent = "";
    } catch (err) {
      const offline = err instanceof CoreOfflineError || err instanceof CoreTimeoutError;
      error.textContent = offline ? UNREACHABLE : FAILED;
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

/**
 * Signed-out screen: the notice and the Sign in button. The button swaps this block for the
 * sign-in form in place, with the same prefilled URL.
 */
export function renderSignedOut(props: SignedOutScreenProps, handlers: PanelHandlers): HTMLElement {
  const box = el("div", undefined, "signed-out");
  box.append(el("p", SIGNED_OUT, "signed-out-text"));
  const signIn = el("button", SIGN_IN_BUTTON, "btn signed-out-sign-in");
  signIn.type = "button";
  signIn.addEventListener("click", () => box.replaceWith(renderSignIn(handlers, { prefill: props.prefill, canCancel: false })));
  box.append(signIn, el("p", NEEDS_DEVICE, "signed-out-note"));
  return box;
}
