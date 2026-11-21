// Minimal type shim for the editor host module "vscode", which is not installed here.
// Runtime values come from the stub in tests/mocks/vscode.ts (vitest alias).
declare module "vscode" {
  export interface Uri {
    toString(): string;
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

  export interface DiagnosticCollection {
    set(uri: Uri, diagnostics: readonly Diagnostic[]): void;
    delete(uri: Uri): void;
  }
}
