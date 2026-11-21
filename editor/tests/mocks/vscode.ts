// Stub of the editor host module, used by vitest through the "vscode" alias in vitest.config.ts.
export const window = {
  showInformationMessage: (_message: string): Promise<undefined> => Promise.resolve(undefined),
};
