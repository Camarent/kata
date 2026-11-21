import { describe, expect, it } from "vitest";
import { installHooks } from "../src/installHooks";
import type { ExecFileFn } from "../src/installHooks";

interface Call {
  file: string;
  args: string[];
  options: { cwd: string };
}

function recordingExec(result: { stdout: string; stderr: string } | Error): { exec: ExecFileFn; calls: Call[] } {
  const calls: Call[] = [];
  const exec: ExecFileFn = (file, args, options) => {
    calls.push({ file, args, options });
    return result instanceof Error ? Promise.reject(result) : Promise.resolve(result);
  };
  return { exec, calls };
}

describe("installHooks", () => {
  it("runs python3 -m kata_device hooks install in the given checkout", async () => {
    const { exec, calls } = recordingExec({ stdout: "hooks written\n", stderr: "" });

    const result = await installHooks("/work/repo", exec);

    expect(calls).toEqual([
      { file: "python3", args: ["-m", "kata_device", "hooks", "install"], options: { cwd: "/work/repo" } },
    ]);
    expect(result).toEqual({ ok: true, output: "hooks written" });
  });

  it("returns ok false with the reason when the command fails, without throwing", async () => {
    const { exec, calls } = recordingExec(new Error("kata hooks: not a git repository"));

    const result = await installHooks("/not/a/repo", exec);

    expect(calls).toHaveLength(1);
    expect(result).toEqual({ ok: false, output: "kata hooks: not a git repository" });
  });

  it("returns ok false when the runner throws synchronously", async () => {
    const exec: ExecFileFn = () => {
      throw "spawn failed";
    };

    const result = await installHooks("/work/repo", exec);

    expect(result).toEqual({ ok: false, output: "spawn failed" });
  });
});
