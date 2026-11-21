// Runs `python3 -m kata_device hooks install` in the workspace checkout (core/kata_device/hooks.py).
// The hook files are written by that command; this module only starts it and reports the outcome.
import { execFile } from "node:child_process";

export interface ExecResult {
  stdout: string;
  stderr: string;
}

export type ExecFileFn = (file: string, args: string[], options: { cwd: string }) => Promise<ExecResult>;

export interface InstallResult {
  ok: boolean;
  output: string;
}

const PYTHON = "python3";
const INSTALL_ARGS = ["-m", "kata_device", "hooks", "install"];

// Default runner over node's execFile. A non-zero exit rejects with the stderr text, or the error message.
export const runExecFile: ExecFileFn = (file, args, options) =>
  new Promise((resolve, reject) => {
    execFile(file, args, options, (error: Error | null, stdout: string, stderr: string) => {
      if (error) {
        reject(new Error(stderr.trim() || error.message));
        return;
      }
      resolve({ stdout, stderr });
    });
  });

// Never throws: a failed run returns ok false with the reason in output.
export async function installHooks(cwd: string, execFileFn: ExecFileFn = runExecFile): Promise<InstallResult> {
  try {
    const { stdout, stderr } = await execFileFn(PYTHON, INSTALL_ARGS, { cwd });
    return { ok: true, output: `${stdout}${stderr}`.trim() };
  } catch (err) {
    return { ok: false, output: err instanceof Error ? err.message : String(err) };
  }
}
