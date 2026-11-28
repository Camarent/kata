# kata

kata is a self-hosted learning companion for people who already know a lot and need to learn adjacent material fast.

Status: early release (0.x). Interfaces may change between releases.

## What it does

- Keeps a model of what each learner already knows, per area, topic and concept. Each concept is marked new, learning or known.
- Organises concepts into areas, topics and concepts. Aliases merge duplicate names, and the API can ignore or delete a concept.
- Reads the lesson page open in the browser when you click "Scan this page", classifies the page, and shows which parts are new to you. The core asks "Which one?" when the topic is unclear. A rescan after the page changes keeps your marks.
- Lets you mark a whole page as known with an "I know this" button.
- Imports a skill list as text to set your marks in bulk.
- Turns knowledge gaps into short practice courses. A course can be regenerated in place, with a preview of what carries over, and opens in the browser through a signed link. The side panel lists, creates and deletes courses; each user has a course limit and unique course names.
- Keeps named concept lists and tracks with goals, progress and pace. Plans a syllabus into time-boxed tracks that share one time budget. Course progress is saved back from the course page through the extension.
- Gives mini quizzes from allowlisted public sources, shows each source's licence, checks answers, and imports exam results after you confirm them.
- Shows a review tree of areas and topics with new, learning and known counts, a searchable, filterable and sortable concept list, and an "Only this page" filter. Marks made while the core is unreachable wait in a queue and sync later.
- Shows short jokes from a fixed list of sources in the page card.
- Writes a short summary of the page into the page card. Summaries are cached per page text.
- Reads PDF pages and images through a sandboxed reader. The reader is built in and off by default.
- Advises inside your own projects: an editor extension, an MCP assistant, a terminal tool, and git hooks that block a commit containing a secret. Every intervention is journaled.
- Keeps secrets out of cloud calls. A secret scanner runs before every cloud request, and a per-user daily spend cap warns before it stops cloud use.
- Runs on machines you control: a server with Docker, TLS over a private network, and nightly encrypted backups. A local model can run on a GPU machine through a worker, and any OpenAI-compatible model server can be added in the host config.

## How it fits together

- **Core service**: the HTTP API, storage in Postgres, accounts and tokens, and the job queue.
- **Worker**: runs model jobs (tagging, course generation) next to a local model server. It polls the core for jobs.
- **Browser extension**: the side panel and the page scanner. It talks only to the core you configure.
- **Trainer**: builds the practice courses from the gaps the core finds.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full map.

## Quick start

### 1. Run the core

You need Python 3.11 or later and either local Postgres binaries or Docker. [`docs/development.md`](docs/development.md) has the full setup.

```
scripts/dev/pg.sh start                       # throwaway Postgres on 127.0.0.1
eval "$(scripts/dev/pg.sh env)"               # point kata at it
PYTHONPATH=core python3 -m kata_core          # with KATA_CONFIG set to your config file
```

Settings come from a TOML file, `config/kata.example.toml` is the template. Every key can be overridden with an environment variable. The full list is in [`docs/configuration.md`](docs/configuration.md). Stop the throwaway Postgres with `scripts/dev/pg.sh stop`.

### 2. Install the extension

Get the build for your browser from the latest release on the [Releases page](https://github.com/Camarent/kata/releases): `kata-extension-<version>-firefox.zip` or `kata-extension-<version>-chrome.zip`. Download `SHA256SUMS` from the same release and check the zip before you unzip it:

```
sha256sum -c SHA256SUMS
```

Or build it yourself: `cd extension && npm ci && npm run build` writes `extension/dist/firefox/` and `extension/dist/chrome/`.

The extension build has no server address in it. You type the server URL in the side panel the first time.

Firefox (128.0 or later):
1. Unzip the Firefox zip into a folder, or use `extension/dist/firefox/`.
2. Open `about:debugging#/runtime/this-firefox`, choose "Load Temporary Add-on", and pick `manifest.json` in that folder.

A temporary add-on lasts until Firefox restarts. After each Firefox restart, load it again with "Load Temporary Add-on". A permanent install needs an add-on signed by Mozilla (AMO); signing is not automated in this repo.

Chrome:
1. Unzip the Chrome zip into a folder, or use `extension/dist/chrome/`.
2. Open `chrome://extensions`, turn on Developer mode, choose "Load unpacked", and pick that folder.

### 3. Connect

1. On the core machine, with `KATA_CONFIG` set to your config file, create the user with `PYTHONPATH=core python3 -m kata_core.auth.admin create-user NAME`. Then print an enrolment code with `PYTHONPATH=core python3 -m kata_core.auth.admin enrol NAME`. The code is shown once and is not stored.
2. Open the kata side panel from the toolbar button.
3. Type the server URL (origin only, for example `http://127.0.0.1:8080`), the enrolment code and a device label, then click Connect. Accept the browser's permission prompt for that address.

Not tested in a real browser yet: the permission prompt, the bridge registration and the course-page bridge (see [`docs/decisions.md`](docs/decisions.md), the entry titled "Extension has no build-time server config").

To scan a page, open a lesson page, open the side panel and click "Scan this page". The page is read only when you click the button; kata never crawls pages.

### Worker (not yet verified end to end)

The worker runs model jobs next to a local Ollama server. The steps are in [`docs/deployment.md`](docs/deployment.md) and the settings in [`docs/configuration.md`](docs/configuration.md). No full run on a real machine is recorded yet.

Model routing: each task class tries the providers in order and the first reply wins. The local model is first; the cloud is second and only runs when its API key env var is set. A class marked `cloud-only` in `[local_capability]` skips the local model. See [`docs/decisions.md`](docs/decisions.md), the entry titled "Routing defaults are local first, cloud by token".

| Task class | Provider order |
|---|---|
| tag | local,anthropic |
| explain | local,anthropic |
| summary | local,anthropic |
| batch | local,anthropic |
| generate_course | local,anthropic |
| extract_syllabus | local,anthropic |
| scan_classify | local,anthropic |
| exam_analyse | local |

## Documentation

- [`docs/INDEX.md`](docs/INDEX.md): index of all documentation.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): how the parts fit together.
- [`docs/development.md`](docs/development.md): set up a machine and run the checks.
- [`docs/release.md`](docs/release.md): how a release is made and checked.
- [`docs/deployment.md`](docs/deployment.md): running the core on a server.
- [`docs/configuration.md`](docs/configuration.md): every setting and its environment variable.
- [`SECURITY.md`](SECURITY.md): how to report a vulnerability.

## Contributing

Work happens on short-lived branches and goes through a pull request. Run the checks locally with `scripts/dev/check-all.sh`; the details are in [`docs/development.md`](docs/development.md).

## License

MIT. See [`LICENSE`](LICENSE).
