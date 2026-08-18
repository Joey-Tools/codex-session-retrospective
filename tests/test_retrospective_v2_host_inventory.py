from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from retrospective_v2 import transport  # noqa: E402


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "remote_host_context_helper.py"


def helper_source(rows: str, *, declaration: str = "HOSTS") -> bytes:
    return f"{declaration} = {{\n{rows}}}\n".encode("ascii")


class HostInventoryTests(unittest.TestCase):
    def test_fixture_inventory_is_canonical_and_round_trips(self) -> None:
        inventory = transport.parse_authenticated_helper_hosts(FIXTURE.read_bytes())

        self.assertEqual(
            (
                "local",
                "BL-mac-mini-m4-hoteng",
                "codex-hoteng-srv-01",
                "hoteng-srv-01",
                "miku-bot-dev",
            ),
            inventory.canonical_hosts,
        )
        self.assertEqual("miku-bot-dev", inventory.resolve("miku-server-dev").host)
        self.assertEqual(
            "/home/hoteng/.codex",
            inventory.resolve("miku-server-dev").codex_root,
        )
        self.assertEqual(
            inventory,
            transport.HostInventory.from_dict(inventory.to_dict()),
        )
        self.assertRegex(inventory.commitment, r"\Asha256:[0-9a-f]{64}\Z")
        self.assertEqual(
            inventory.commitment,
            transport.require_inventory_commitment(
                inventory,
                inventory.commitment,
            ),
        )

    def test_annotated_static_hosts_assignment_is_supported(self) -> None:
        source = helper_source(
            "    'local': {'kind': 'local', 'label': 'local', "
            "'codex_root': '~/.codex'},\n",
            declaration="HOSTS: dict[str, dict[str, str]]",
        )

        inventory = transport.parse_authenticated_helper_hosts(source)

        self.assertEqual(("local",), inventory.canonical_hosts)

    def test_dynamic_reassigned_or_mutated_hosts_are_rejected(self) -> None:
        static = (
            "HOSTS = {'local': {'kind': 'local', 'label': 'local', "
            "'codex_root': '~/.codex'}}\n"
        )
        cases = {
            "dynamic": b"HOSTS = build_hosts()\n",
            "duplicate": (static + static).encode("ascii"),
            "subscript mutation": (static + "HOSTS['other'] = {}\n").encode("ascii"),
            "nested field mutation": (
                static + "HOSTS['local']['codex_root'] = '~/alternate'\n"
            ).encode("ascii"),
            "nested row update": (
                static + "HOSTS['local'].update({'codex_root': '~/alternate'})\n"
            ).encode("ascii"),
            "attribute mutation": (static + "HOSTS.other = {}\n").encode("ascii"),
            "update call": (static + "HOSTS.update({})\n").encode("ascii"),
            "clear call": (static + "HOSTS.clear()\n").encode("ascii"),
            "unbound mutator": (
                static + "dict.__setitem__(HOSTS, 'other', {})\n"
            ).encode("ascii"),
            "container alias": (static + "alias = HOSTS\n").encode("ascii"),
            "row alias": (static + "row = HOSTS['local']\n").encode("ascii"),
            "delete": (static + "del HOSTS\n").encode("ascii"),
        }
        for label, source in cases.items():
            with (
                self.subTest(label=label),
                self.assertRaises(transport.HostInventoryError),
            ):
                transport.parse_authenticated_helper_hosts(source)

    def test_closed_membership_and_string_field_reads_are_supported(self) -> None:
        source = helper_source(
            "    'local': {'kind': 'local', 'label': 'local', "
            "'codex_root': '~/.codex'},\n"
        ) + (
            b"def resolve(value):\n"
            b"    if value not in HOSTS:\n"
            b"        raise ValueError(value)\n"
            b"    return HOSTS[value]['label']\n"
        )

        inventory = transport.parse_authenticated_helper_hosts(source)

        self.assertEqual(("local",), inventory.canonical_hosts)

    def test_local_host_binding_is_exact(self) -> None:
        cases = {
            "alternate label": (
                "    'workstation': {'kind': 'local', 'label': 'workstation', "
                "'codex_root': '~/.codex'},\n"
            ),
            "absolute root": (
                "    'local': {'kind': 'local', 'label': 'local', "
                "'codex_root': '/Users/hoteng/.codex'},\n"
            ),
            "alternate home root": (
                "    'local': {'kind': 'local', 'label': 'local', "
                "'codex_root': '~/alternate'},\n"
            ),
        }
        for label, rows in cases.items():
            with (
                self.subTest(label=label),
                self.assertRaisesRegex(
                    transport.HostInventoryError,
                    "local host binding is unsupported",
                ),
            ):
                transport.parse_authenticated_helper_hosts(helper_source(rows))

    def test_row_shape_route_and_alias_properties_are_closed(self) -> None:
        local = (
            "    'local': {'kind': 'local', 'label': 'local', "
            "'codex_root': '~/.codex'},\n"
        )
        cases = {
            "extra field": local + "    'remote': {'kind': 'ssh', 'label': 'remote', "
            "'ssh_target': 'remote', 'codex_root': '/home/r/.codex', "
            "'port': '22'},\n",
            "relative remote root": local
            + "    'remote': {'kind': 'ssh', 'label': 'remote', "
            "'ssh_target': 'remote', 'codex_root': '~/.codex'},\n",
            "missing local": "    'remote': {'kind': 'ssh', 'label': 'remote', "
            "'ssh_target': 'remote', 'codex_root': '/home/r/.codex'},\n",
            "alias drift": local + "    'remote': {'kind': 'ssh', 'label': 'remote', "
            "'ssh_target': 'remote', 'codex_root': '/home/r/.codex'},\n"
            "    'alias': {'kind': 'ssh', 'label': 'remote', "
            "'ssh_target': 'other', 'codex_root': '/home/r/.codex'},\n",
            "unknown alias target": local
            + "    'alias': {'kind': 'ssh', 'label': 'missing', "
            "'ssh_target': 'missing', 'codex_root': '/home/r/.codex'},\n",
        }
        for label, rows in cases.items():
            with (
                self.subTest(label=label),
                self.assertRaises(transport.HostInventoryError),
            ):
                transport.parse_authenticated_helper_hosts(helper_source(rows))

    def test_retained_inventory_rejects_noncanonical_order_or_commitment(self) -> None:
        inventory = transport.parse_authenticated_helper_hosts(FIXTURE.read_bytes())
        retained = inventory.to_dict()
        retained["canonical_entries"] = list(reversed(retained["canonical_entries"]))
        with self.assertRaises(transport.HostInventoryError):
            transport.HostInventory.from_dict(retained)
        with self.assertRaises(transport.HostInventoryError):
            transport.require_inventory_commitment(
                inventory,
                "sha256:" + "0" * 64,
            )


if __name__ == "__main__":
    unittest.main()
