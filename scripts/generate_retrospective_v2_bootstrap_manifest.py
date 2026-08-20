#!/usr/bin/env python3
"""Check or update the closed source manifest in the v2 entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
ENTRYPOINT = SCRIPTS / "session_retrospective_v2_runtime.py"
BOOTSTRAP_LAUNCHER = "session_retrospective_v2.py"
PACKAGE = SCRIPTS / "retrospective_v2"
BEGIN = "    # BEGIN GENERATED RETROSPECTIVE V2 SOURCE MANIFEST\n"
END = "    # END GENERATED RETROSPECTIVE V2 SOURCE MANIFEST\n"
DIRECT_HELPERS = (
    "session_retrospective_v2_export.py",
    "session_retrospective_v2_transcript.py",
)


def _regular_python_names(directory: Path) -> tuple[str, ...]:
    paths = sorted(directory.glob("*.py"), key=lambda path: path.name)
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise SystemExit("bootstrap manifest sources must be regular files")
    return tuple(path.name for path in paths)


def _tuple_source(name: str, values: tuple[str, ...]) -> list[str]:
    return [
        f"    {name} = (\n",
        *(f"        {json.dumps(value)},\n" for value in values),
        "    )\n",
    ]


def expected_block() -> str:
    package = _regular_python_names(PACKAGE)
    if "__init__.py" not in package or "cli.py" not in package:
        raise SystemExit("bootstrap package inventory is incomplete")
    root_sources = tuple(
        name
        for name in _regular_python_names(SCRIPTS)
        if name.startswith("session_retrospective_v2")
        and name not in {BOOTSTRAP_LAUNCHER, ENTRYPOINT.name}
    )
    if any(name not in root_sources for name in DIRECT_HELPERS):
        raise SystemExit("bootstrap direct helper inventory is incomplete")
    support = tuple(name for name in root_sources if name not in DIRECT_HELPERS)
    return "".join(
        [
            BEGIN,
            *_tuple_source("_PACKAGE_SOURCE_MANIFEST", package),
            *_tuple_source("_ROOT_HELPER_SOURCE_MANIFEST", DIRECT_HELPERS),
            *_tuple_source("_ROOT_SUPPORT_SOURCE_MANIFEST", support),
            END,
        ]
    )


def update(*, write: bool) -> int:
    source = ENTRYPOINT.read_text(encoding="utf-8")
    start = source.find(BEGIN)
    end = source.find(END, start + len(BEGIN))
    if start < 0 or end < 0 or source.find(BEGIN, start + 1) >= 0:
        raise SystemExit("bootstrap manifest markers are invalid")
    end += len(END)
    expected = expected_block()
    updated = source[:start] + expected + source[end:]
    if updated == source:
        return 0
    if not write:
        print(
            "bootstrap manifest is stale; run "
            "scripts/generate_retrospective_v2_bootstrap_manifest.py --write"
        )
        return 1
    ENTRYPOINT.write_text(updated, encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    return update(write=parser.parse_args().write)


if __name__ == "__main__":
    raise SystemExit(main())
