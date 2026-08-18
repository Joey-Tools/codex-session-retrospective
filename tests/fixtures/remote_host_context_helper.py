#!/usr/bin/env python3
"""Static test fixture for remote-host-context executable commitments."""

HOSTS = {
    "local": {"kind": "local", "label": "local", "codex_root": "~/.codex"},
    "BL-mac-mini-m4-hoteng": {
        "kind": "ssh",
        "label": "BL-mac-mini-m4-hoteng",
        "ssh_target": "BL-mac-mini-m4-hoteng",
        "codex_root": "/Users/hoteng/.codex",
    },
    "miku-bot-dev": {
        "kind": "ssh",
        "label": "miku-bot-dev",
        "ssh_target": "miku-bot-dev",
        "codex_root": "/home/hoteng/.codex",
    },
    "miku-server-dev": {
        "kind": "ssh",
        "label": "miku-bot-dev",
        "ssh_target": "miku-bot-dev",
        "codex_root": "/home/hoteng/.codex",
    },
    "hoteng-srv-01": {
        "kind": "ssh",
        "label": "hoteng-srv-01",
        "ssh_target": "hoteng-srv-01",
        "codex_root": "/home/hoteng/.codex",
    },
    "codex-hoteng-srv-01": {
        "kind": "ssh",
        "label": "codex-hoteng-srv-01",
        "ssh_target": "codex-hoteng-srv-01",
        "codex_root": "/home/codex/.codex",
    },
}

raise SystemExit("remote-host-context commitment fixture must not be executed")
