import type { PanelHandlers } from "../../sidepanel";
import { renderConnectionDetail, type ConnectionDetailProps } from "./connection";
import { renderOfflineQueue, type OfflineQueueProps } from "./offlineQueue";
import { renderSignIn, renderSignedOut, type SignInScreenProps, type SignedOutScreenProps } from "./signin";

/** Props each panel screen id takes. */
export interface PanelScreenProps {
  signin: SignInScreenProps;
  "signed-out": SignedOutScreenProps;
  "conn-detail": ConnectionDetailProps;
  "offline-queue": OfflineQueueProps;
}

/** Id of a panel screen, as named in the screen inventory. */
export type PanelScreenId = keyof PanelScreenProps;

/** Draws one screen from its props; ctx carries the user actions. */
export type ScreenRender<Props, Ctx> = (props: Props, ctx: Ctx) => HTMLElement;

/** Screen id to render function: one entry for every screen id the router knows. */
export type ScreenRegistry<Props extends object, Ctx> = { [K in keyof Props]: ScreenRender<Props[K], Ctx> };

/** Builds a router that draws the screen with a given id from its registry entry. */
export function createRouter<Props extends object, Ctx>(
  registry: ScreenRegistry<Props, Ctx>,
): <K extends keyof Props>(id: K, props: Props[K], ctx: Ctx) => HTMLElement {
  return (id, props, ctx) => registry[id](props, ctx);
}

/** The panel's screens. task-21 extends this registry when it wires the rest. */
export const PANEL_SCREENS: ScreenRegistry<PanelScreenProps, PanelHandlers> = {
  signin: (props, handlers) => renderSignIn(handlers, props),
  "signed-out": (props, handlers) => renderSignedOut(props, handlers),
  "conn-detail": (props, handlers) => renderConnectionDetail(props, handlers),
  "offline-queue": (props, handlers) => renderOfflineQueue(props, handlers),
};

/** Draws the panel screen `id` with `props`; returns the element to append. */
export const routeScreen = createRouter<PanelScreenProps, PanelHandlers>(PANEL_SCREENS);
