// Stub of the editor host module, used by vitest through the "vscode" alias in vitest.config.ts.
export const window = {
  showInformationMessage: (_message: string): Promise<undefined> => Promise.resolve(undefined),
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
