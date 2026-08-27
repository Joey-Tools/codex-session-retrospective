"""Hold one config-free keyring snapshot until the parent terminates us."""

from __future__ import annotations

from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from retrospective_v2 import gpg_keyring_snapshot, temporary_paths  # noqa: E402


def main() -> int:
    source, snapshot_root, source_root = map(Path, sys.argv[1:4])
    temporary_paths.PUBLISHER_KEYRING_SNAPSHOT_TEMP_ROOT = snapshot_root
    temporary_paths.local_codex_root = lambda: source_root
    with gpg_keyring_snapshot.config_free_keyring_snapshot(source) as snapshot:
        print(snapshot, flush=True)
        while True:
            time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
