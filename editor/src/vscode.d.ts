// Minimal type shim for the editor host module "vscode", which is not installed here.
// Runtime values come from the stub in tests/mocks/vscode.ts (vitest alias).
declare module "vscode" {
  export interface Disposable {
    dispose(): void;
  }

  export type Event<T> = (listener: (e: T) => unknown) => Disposable;

  export interface Uri {
    toString(): string;
    readonly fsPath: string;
  }

  export class Position {
    readonly line: number;
    readonly character: number;
    constructor(line: number, character: number);
  }

  export class Range {
    readonly start: Position;
    readonly end: Position;
    constructor(startLine: number, startCharacter: number, endLine: number, endCharacter: number);
  }

  export enum DiagnosticSeverity {
    Error = 0,
    Warning = 1,
    Information = 2,
    Hint = 3,
  }

  export class Diagnostic {
    range: Range;
    message: string;
    severity: DiagnosticSeverity;
    constructor(range: Range, message: string, severity?: DiagnosticSeverity);
  }

  export interface DiagnosticCollection extends Disposable {
    set(uri: Uri, diagnostics: readonly Diagnostic[]): void;
    delete(uri: Uri): void;
  }

  export interface TextDocument {
    readonly uri: Uri;
    readonly languageId: string;
    getText(): string;
  }

  export interface WebviewView {
    readonly webview: { html: string };
  }

  export interface WebviewViewProvider {
    resolveWebviewView(view: WebviewView): void;
  }

  export interface ExtensionContext {
    readonly subscriptions: Disposable[];
  }

  export const window: {
    showInformationMessage(message: string): Promise<unknown>;
    showQuickPick(items: readonly string[]): Promise<string | undefined>;
    registerWebviewViewProvider(viewId: string, provider: WebviewViewProvider): Disposable;
  };

  export const commands: {
    registerCommand(id: string, callback: (...args: unknown[]) => unknown): Disposable;
  };

  export const workspace: {
    readonly workspaceFolders: readonly { readonly uri: Uri }[] | undefined;
    getConfiguration(section?: string): { get(key: string): unknown };
    readonly onDidSaveTextDocument: Event<TextDocument>;
  };

  export const languages: {
    createDiagnosticCollection(name?: string): DiagnosticCollection;
  };
}
