// Stub of the editor host module, used by vitest through the "vscode" alias in vitest.config.ts.
// The registrations made by the extension are recorded in `host`; resetHost() clears them.
interface Disposed {
  dispose(): void;
}

export interface HostDiagnosticCall {
  op: "set" | "delete";
  uri: unknown;
  diagnostics?: unknown[];
}

export const host = {
  commands: new Map<string, (...args: unknown[]) => unknown>(),
  webviewProviders: new Map<string, { resolveWebviewView(view: { webview: { html: string } }): void }>(),
  saveListeners: [] as Array<(doc: unknown) => unknown>,
  diagnosticCalls: [] as HostDiagnosticCall[],
  diagnosticCollections: [] as string[],
  settings: {} as Record<string, unknown>,
  workspaceRoot: undefined as string | undefined,
};

export function resetHost(): void {
  host.commands.clear();
  host.webviewProviders.clear();
  host.saveListeners.length = 0;
  host.diagnosticCalls.length = 0;
  host.diagnosticCollections.length = 0;
  host.settings = {};
  host.workspaceRoot = undefined;
}

function disposable(fn: () => void): Disposed {
  return { dispose: fn };
}

export const window = {
  showInformationMessage: (_message: string): Promise<undefined> => Promise.resolve(undefined),
  registerWebviewViewProvider: (
    viewId: string,
    provider: { resolveWebviewView(view: { webview: { html: string } }): void },
  ): Disposed => {
    host.webviewProviders.set(viewId, provider);
    return disposable(() => host.webviewProviders.delete(viewId));
  },
};

export const commands = {
  registerCommand: (id: string, callback: (...args: unknown[]) => unknown): Disposed => {
    host.commands.set(id, callback);
    return disposable(() => host.commands.delete(id));
  },
};

export const workspace = {
  get workspaceFolders(): Array<{ uri: { fsPath: string } }> | undefined {
    return host.workspaceRoot === undefined ? undefined : [{ uri: { fsPath: host.workspaceRoot } }];
  },
  getConfiguration: (_section?: string) => ({ get: (key: string): unknown => host.settings[key] }),
  onDidSaveTextDocument: (listener: (doc: unknown) => unknown): Disposed => {
    host.saveListeners.push(listener);
    return disposable(() => {
      const index = host.saveListeners.indexOf(listener);
      if (index >= 0) host.saveListeners.splice(index, 1);
    });
  },
};

export const languages = {
  createDiagnosticCollection: (name?: string) => {
    host.diagnosticCollections.push(name ?? "");
    return {
      set: (uri: unknown, diagnostics: unknown[]): void => {
        host.diagnosticCalls.push({ op: "set", uri, diagnostics });
      },
      delete: (uri: unknown): void => {
        host.diagnosticCalls.push({ op: "delete", uri });
      },
    };
  },
};

export class Position {
  constructor(
    public readonly line: number,
    public readonly character: number,
  ) {}
}

export class Range {
  readonly start: Position;
  readonly end: Position;
  constructor(startLine: number, startCharacter: number, endLine: number, endCharacter: number) {
    this.start = new Position(startLine, startCharacter);
    this.end = new Position(endLine, endCharacter);
  }
}

export enum DiagnosticSeverity {
  Error = 0,
  Warning = 1,
  Information = 2,
  Hint = 3,
}

export class Diagnostic {
  constructor(
    public readonly range: Range,
    public readonly message: string,
    public readonly severity: DiagnosticSeverity = DiagnosticSeverity.Error,
  ) {}
}
