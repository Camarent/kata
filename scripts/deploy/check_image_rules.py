"""Check deploy/Dockerfile and .dockerignore against the image rules.

Rules, named at the start of each failure line:
  unpinned-from         a FROM image has no digest and no tag, or uses :latest
  root-user             the final stage's last USER is root or 0
  missing-user          the final stage has no USER
  missing-healthcheck   the final stage has no HEALTHCHECK (NONE does not count)
  dockerignore-missing  .dockerignore has no entry for .git, .env files or secrets
  secret-copy           a COPY or ADD source is a .env file or a secret path

hadolint is not run by the gate: the script prints a hint to run it by hand.
Exit 0 when every rule passes, 1 when a rule fails, 2 when an input cannot be read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run with -I, which leaves the script directory off sys.path: add it to find _rules.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _rules import _image_pinned

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "deploy" / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
HADOLINT_HINT = "hint: hadolint is not run by the gate; run 'hadolint deploy/Dockerfile' manually"

# Each requirement: a label and the .dockerignore lines that satisfy it.
REQUIRED_IGNORES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (".git", (".git",)),
    (".env files", (".env", "**/.env", "*.env", "**/*.env")),
    ("secrets", ("secrets", "**/secrets")),
)
SECRET_DIR_NAMES = frozenset({"secret", "secrets"})
ROOT_USERS = frozenset({"root", "0"})

# (KEYWORD, argument text) for one logical Dockerfile instruction.
Instruction = tuple[str, str]


def _instruction(full: str) -> Instruction:
    keyword, _, rest = full.strip().partition(" ")
    return keyword.upper(), rest.strip()


def instructions(text: str) -> list[Instruction]:
    """Logical instructions: comments and blank lines dropped, backslash continuations joined."""
    out: list[Instruction] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        out.append(_instruction(pending + line))
        pending = ""
    if pending.strip():
        out.append(_instruction(pending))
    return out


def _copy_sources(rest: str) -> list[str]:
    """Source paths of a COPY or ADD (shell or JSON form); the last token is the destination."""
    cleaned = rest
    for char in '[],"':
        cleaned = cleaned.replace(char, " ")
    tokens = [token for token in cleaned.split() if not token.startswith("--")]
    return tokens[:-1]


def _is_secret_path(source: str) -> bool:
    parts = [part for part in source.split("/") if part not in ("", ".")]
    if not parts:
        return False
    name = parts[-1]
    if name == ".env" or name.endswith(".env") or name.startswith(".env."):
        return True
    return any(part in SECRET_DIR_NAMES for part in parts)


def check(dockerfile: str, dockerignore: str) -> list[str]:
    """One 'rule: message' line per failed rule; an empty list when the files pass."""
    problems: list[str] = []
    aliases: set[str] = set()
    final_stage: list[Instruction] = []
    for keyword, rest in instructions(dockerfile):
        if keyword == "FROM":
            tokens = [token for token in rest.split() if not token.startswith("--")]
            image = tokens[0] if tokens else ""
            if len(tokens) >= 3 and tokens[1].upper() == "AS":
                aliases.add(tokens[2].lower())
            # A FROM of an earlier stage's alias names that stage, not a registry image.
            if image.lower() not in aliases and not _image_pinned(image):
                problems.append(f"unpinned-from: FROM {image} lacks a digest or non-latest tag")
            final_stage = []
            continue
        final_stage.append((keyword, rest))
        if keyword in ("COPY", "ADD"):
            for source in _copy_sources(rest):
                if _is_secret_path(source):
                    problems.append(f"secret-copy: {keyword} copies {source}")

    users = [rest for keyword, rest in final_stage if keyword == "USER"]
    if not users:
        problems.append("missing-user: final stage has no USER")
    elif users[-1].split(":")[0] in ROOT_USERS:
        problems.append(f"root-user: final stage runs as {users[-1]}")
    healthchecks = [
        rest for keyword, rest in final_stage if keyword == "HEALTHCHECK" and rest.upper() != "NONE"
    ]
    if not healthchecks:
        problems.append("missing-healthcheck: final stage has no HEALTHCHECK")

    entries = {
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for label, accepted in REQUIRED_IGNORES:
        if not entries.intersection(accepted):
            problems.append(f"dockerignore-missing: .dockerignore has no entry for {label}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check image rules in deploy/Dockerfile and .dockerignore.")
    parser.add_argument("--dockerfile", type=Path, default=DOCKERFILE)
    parser.add_argument("--dockerignore", type=Path, default=DOCKERIGNORE)
    args = parser.parse_args(argv)
    try:
        dockerfile = args.dockerfile.read_text(encoding="utf-8")
        dockerignore = args.dockerignore.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check_image_rules: cannot read input: {exc}", file=sys.stderr)
        return 2
    problems = check(dockerfile, dockerignore)
    for problem in problems:
        print(problem)
    print(HADOLINT_HINT)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
