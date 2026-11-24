# Releases

Every change after the first release ships as a release made by the pipeline. This page covers the order of steps, how a tag becomes a GitHub release, and how the VM gets the new code.

## Version

The version lives in five files: `pyproject.toml`, `extension/package.json`, the root entry of `extension/package-lock.json`, `extension/manifest.base.json`, and the `__version__` line of `core/kata_core/__init__.py`. The code is MIT licensed (`LICENSE`). `pyproject.toml` and `extension/package.json` both carry `"MIT"` as their licence field. A release does not change the licence.

The repo started at `0.0.0` on purpose: the first release was `v0.1.0`, a minor bump. The current version is `0.1.10`. Audits and fix tasks must not change the version.

## Release steps

1. Merge the change into `master` (squash merge).
2. When a release is due, bump the version from the repo root. Run `scripts/release/bump_version.sh current` to read the version now. Then run `scripts/release/bump_version.sh set OLD NEW "ENTRY"` with the old and new versions and a one-line CHANGELOG entry. The script moves the version in the five files above and adds the entry under a dated `## [X.Y.Z]` heading in `CHANGELOG.md`. Review the changed files and commit them.
3. Create the tag `vX.Y.Z` on the release commit and push it: `git tag vX.Y.Z`, then `git push origin vX.Y.Z`.
4. The tag triggers `.github/workflows/release-extension.yml` (see below).
5. The VM takes the new code (see "VM" below).

When no release is due, skip steps 2 to 4: no version change and no tag.

The hook moves the version only in its own entries. A dependency that has the same number is never touched.

## Tag triggers the release workflow

A push of a `v*` tag runs `.github/workflows/release-extension.yml`:

1. Runs the extension tests (`npm --prefix extension test`).
2. Sets `KATA_EXTENSION_VERSION` from the tag (`v0.1.0` gives `0.1.0`). The build uses it in place of the manifest version.
3. Builds both browsers (`npm --prefix extension run build`).
4. Zips each build with `scripts/release/make_zip.py`: `kata-extension-<version>-firefox.zip` and `kata-extension-<version>-chrome.zip`.
5. Writes `SHA256SUMS` for the two zips.
6. Creates the GitHub release for the tag, or uploads to it when it already exists (`--clobber`). It uploads both zips and `SHA256SUMS`.

A manual run (`workflow_dispatch`) runs the tests only. It builds nothing and touches no release.

To check a download, compare the zip with its line in `SHA256SUMS`:

```
sha256sum -c SHA256SUMS
```

## Install from a release

The extension build has no server address in it. Download the zip for your browser from the [Releases page](https://github.com/Camarent/kata/releases), check it against `SHA256SUMS`, and follow "Install the extension" in `README.md`.

## VM

The VM runs the core from a container image built on dev. It does not use the extension zips.

1. Check out the new tag on the dev machine with a clean tree.
2. Take a dump first (see `docs/deployment.md`, Backup).
3. Ship from dev: `KATA_SHIP_TARGET=<user>@<host> KATA_SHIP_DIR=/opt/kata/deploy KATA_SHIP_ENV_FILE=env/vm.env deploy/ship.sh`. The ship rebuilds the image, restarts the stack and runs the deep health check.
4. Reload the extension and check that it connects to the new core.

The full steps, rollback and the variables are in `docs/deployment.md`.

## Checks before a tag

- `scripts/dev/check-all.sh` is green on `master`.
- `CHANGELOG.md` has the entry for the version under `## [X.Y.Z]`, with `## [Unreleased]` above it.
- The five version fields agree (`tests/scripts/test_version_consistency.py` checks this).
