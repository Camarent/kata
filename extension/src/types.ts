/** A readable block of page text, optionally bound to its DOM element. */
export interface Block {
  id: string;
  text: string;
  el?: HTMLElement;
}

/** Connection to the local kata service. */
export interface Session {
  baseUrl: string;
  token: string;
}
