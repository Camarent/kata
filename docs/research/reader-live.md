# Reader live probe

## Files

| file | media type | status | pages |
|---|---|---|---|
| diagram_real.pdf | application/pdf | done | 2 |
| scan_real.png | image/png | done | 1 |
| scanned_real.pdf | application/pdf | done | 1 |

## Sandbox checks

connect: blocked
write: blocked

## Findings

- core/kata_core/api/routes/jobs.py:48 and :120: `ClaimResponse` has no `kind`, so `GET /jobs/next` never tells the worker the job kind. `worker/kata_worker/core_client.py:140` then defaults it to `tag`, and every leased `reader.extract` job ran the tag handler and failed (`job failed while tagging`). The end to end run reached `done` only on a throwaway image with `kind` added to `ClaimResponse`; the stage tree is unchanged. Fix: return `kind=job.kind`, and update `docs/api.md` (`/jobs/next` reply).
- deploy/Dockerfile (no `/spool/in`, `/spool/out`; `USER kata` at line 67) with deploy/compose.yaml `reader-in` and `reader-out` volumes: the named volumes mount root-owned, so the worker (uid 10001) cannot write `/spool/in` and the reader cannot write `/spool/out`. The first run failed every feed (`feed_error`). The rerun worked only after the volumes were chowned to uid 10001 by hand. Fix: create both directories owned by `kata` in the image, or set the volume owner.
- scripts/dev/reader_probe.py:281 (`check_report`) and `--make-corpus`: the checker needs every Files row to be `done`, but the synthetic hostile files are refused by design. With the volumes fixed, the reader refused them correctly: `bad_magic.pdf` and `empty.pdf` gave `bad_type`; `huge_declared.png`, `trailing_junk.png` and `truncated.pdf` gave `bad_file`. No crash, no traceback. The table above lists only the real files; the hostile rows cannot pass the checker. Fix: let the checker expect a refusal status for the hostile corpus files.
- Sandbox: no FAIL and no OPEN check; `connect` and `write` were both blocked from inside the reader container.
- End to end: a scanned PDF with no text layer went through core, worker, reader and the cloud vision model (`claude-haiku-5-5`, `[reader] enabled = true` in a temp config only) and came back as the transcribed text, document status `done`, 1 page. `deploy/kata.host.toml` and `config/kata.example.toml` keep `enabled = false`.

## End to end

Status: done
