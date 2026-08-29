"""Unit tests for the Hwahap project-agent installer."""

from __future__ import annotations

import importlib.util
import io
import os
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("install_project_agents.py")
MODULE_SPEC = importlib.util.spec_from_file_location("install_project_agents", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
installer = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(installer)


class ProjectAgentInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = "/private/tmp" if Path("/private/tmp").is_dir() else None
        self.tempdir = tempfile.TemporaryDirectory(dir=temp_root)
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def install(self, workspace: Path | None = None) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            installer.install(str(workspace or self.root))
        return output.getvalue()

    def assert_install_error(self, code: str, workspace: Path | None = None) -> None:
        with self.assertRaises(installer.InstallError) as raised:
            self.install(workspace)
        self.assertEqual(raised.exception.code, code)

    def prepare_partial_workspace(self, name: str) -> tuple[Path, list[tuple[Path, bytes]], Path, bytes]:
        workspace = self.root / name
        agents = workspace / ".codex" / "agents"
        agents.mkdir(parents=True)
        profiles = installer.source_profiles()
        identical = agents / profiles[0][0].name
        identical.write_bytes(profiles[0][1])
        unrelated = agents / "user-agent.toml"
        unrelated.write_bytes(b"name = 'unrelated'\n")
        config = workspace / ".codex" / "config.toml"
        config.write_bytes(b"[project]\nname = 'preserve'\n")
        return workspace, profiles, unrelated, config.read_bytes()

    def install_with_open_failure(self, workspace: Path, profiles: list[tuple[Path, bytes]], fail_index: int, failure: str) -> None:
        original_open = Path.open
        original_os_open = installer.os.open
        original_fdopen = installer.os.fdopen
        calls = 0
        agents = workspace / ".codex" / "agents"
        faulty_fd = -1

        class FaultyHandle:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, exc_type, exc, traceback):
                result = self.handle.__exit__(exc_type, exc, traceback)
                if failure == "write-replace" and exc_type is not None:
                    prior = agents / profiles[1][0].name
                    os.unlink(prior)
                    with original_open(prior, "wb") as replacement:
                        replacement.write(b"replacement-canary")
                if failure == "close" and exc_type is None:
                    raise OSError("close-canary")
                return result

            def write(self, data):
                result = self.handle.write(data)
                if failure in ("write", "write-replace"):
                    raise OSError("write-canary")
                return result

        def open_with_failure(name, flags, mode=0o777, *, dir_fd=None):
            nonlocal calls, faulty_fd
            if not flags & os.O_CREAT or not flags & os.O_EXCL:
                return original_os_open(name, flags, mode, dir_fd=dir_fd)
            calls += 1
            if calls == fail_index and failure == "race":
                path = agents / name
                with original_open(path, "wb") as handle:
                    handle.write(b"race-canary")
                raise FileExistsError("race-canary")
            if calls == fail_index and failure == "late-extra":
                with original_open(agents / "hwahap-extra.toml", "wb") as handle:
                    handle.write(b"extra-canary")
            if calls == fail_index and failure == "race-replace":
                prior = agents / profiles[1][0].name
                os.unlink(prior)
                with original_open(prior, "wb") as handle:
                    handle.write(b"replacement-canary")
                path = agents / name
                with original_open(path, "wb") as handle:
                    handle.write(b"race-canary")
                raise FileExistsError("race-canary")
            fd = original_os_open(name, flags, mode, dir_fd=dir_fd)
            if calls == fail_index:
                faulty_fd = fd
            return fd

        def fdopen_with_failure(fd, *args, **kwargs):
            handle = original_fdopen(fd, *args, **kwargs)
            return FaultyHandle(handle) if fd == faulty_fd else handle

        with patch.object(installer, "source_profiles", return_value=profiles), patch.object(installer.os, "open", new=open_with_failure), patch.object(installer.os, "fdopen", new=fdopen_with_failure):
            installer.install(str(workspace))

    def test_source_profiles_have_exact_contract_metadata(self) -> None:
        expected = {
            "hwahap-luna-implementer.toml": ("hwahap-luna-implementer", "gpt-5.6-luna", "high", "workspace-write", None, None),
            "hwahap-luna-verifier.toml": ("hwahap-luna-verifier", "gpt-5.6-luna", "xhigh", "read-only", None, None),
            "hwahap-sol-final-reviewer.toml": ("hwahap-sol-final-reviewer", "gpt-5.6-sol", None, "read-only", None, None),
            "hwahap-sol-orchestrator.toml": ("hwahap-sol-orchestrator", "gpt-5.6-sol", "xhigh", "workspace-write", "fast", True),
            "hwahap-terra-scope-reviewer.toml": ("hwahap-terra-scope-reviewer", "gpt-5.6-terra", "xhigh", "read-only", None, None),
        }
        profiles = installer.source_profiles()
        self.assertEqual({path.name for path, _ in profiles}, set(expected))
        for path, raw in profiles:
            value = tomllib.loads(raw.decode("utf-8"))
            self.assertEqual(
                (value["name"], value.get("model"), value.get("model_reasoning_effort"),
                 value.get("sandbox_mode"), value.get("service_tier"),
                 value.get("features", {}).get("fast_mode")),
                expected[path.name],
            )

    def test_source_profiles_describe_snapshot_handoff_contract(self) -> None:
        text = {path.name: raw.decode("utf-8") for path, raw in installer.source_profiles()}
        for phrase in ("only the changed paths and bounded", "Do not claim an official digest or `diff_snapshot`",
                       "after the base and target commits"):
            self.assertIn(phrase, text["hwahap-luna-implementer.toml"])
        for phrase in ("actual six-field", "--base-commit", "both reviewers have received"):
            self.assertIn(phrase, text["hwahap-sol-orchestrator.toml"])
        for name in ("hwahap-luna-verifier.toml", "hwahap-terra-scope-reviewer.toml"):
            self.assertIn("full six-field `diff_snapshot`", text[name])
            self.assertIn("actual", text[name])
            self.assertIn("Git", text[name])
            self.assertIn("diff", text[name])
            self.assertIn("`diff_digest`", text[name])
        for phrase in ("full six-field `diff_snapshot`", "same full valid final snapshot", "verified digest"):
            self.assertIn(phrase, text["hwahap-sol-final-reviewer.toml"])
        for phrase in ("evidence and a diff digest",):
            self.assertNotIn(phrase, text["hwahap-luna-implementer.toml"])
        self.assertNotIn("contract and diff digest", text["hwahap-luna-verifier.toml"])
        self.assertNotIn("same locked contract and diff digest", text["hwahap-terra-scope-reviewer.toml"])
        self.assertNotIn("exact final `diff_digest`", text["hwahap-sol-final-reviewer.toml"])
        self.assertNotIn("exact final diff digest only", text["hwahap-sol-final-reviewer.toml"])
        self.assertNotIn("Give the final reviewer the exact final diff digest.", text["hwahap-sol-orchestrator.toml"])
        self.assertNotIn("latest Luna verifier thread/digest", text["hwahap-sol-orchestrator.toml"])

    def test_fresh_install_copies_all_profiles_byte_identically(self) -> None:
        self.install()
        expected = {path.name: raw for path, raw in installer.source_profiles()}
        targets = tuple((self.root / ".codex" / "agents").glob("*.toml"))
        actual = {path.name: path.read_bytes() for path in targets}
        self.assertEqual(actual, expected)
        self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in targets))

    def test_second_install_is_idempotent(self) -> None:
        self.install()
        agents = self.root / ".codex" / "agents"
        before = {path.name: path.read_bytes() for path in agents.glob("*.toml")}
        output = self.install()
        after = {path.name: path.read_bytes() for path in agents.glob("*.toml")}
        self.assertEqual(after, before)
        self.assertIn("installed=0", output)
        self.assertIn("skipped=5", output)

    def test_source_set_and_metadata_are_validated_before_workspace_mutation(self) -> None:
        source = self.root / "one-profile-source"
        source.mkdir()
        source.joinpath("hwahap-luna-implementer.toml").write_bytes(
            installer.source_profiles()[0][1])
        with patch.object(installer, "PROFILE_DIR", source):
            self.assert_install_error("HW_AGENT_SOURCE_INVALID")
        self.assertFalse((self.root / ".codex").exists())

    def test_source_profile_instructions_are_digest_pinned(self) -> None:
        source = self.root / "instruction-tamper-source"
        source.mkdir()
        for path, raw in installer.source_profiles():
            if path.name == "hwahap-luna-verifier.toml":
                raw = raw.replace(b"independent verifier", b"independent executor")
            (source / path.name).write_bytes(raw)
        with self.assertRaises(installer.InstallError) as raised:
            installer.source_profiles(source)
        self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
        source = self.root / "bad-metadata-source"
        source.mkdir()
        for path, raw in installer.source_profiles():
            source.joinpath(path.name).write_bytes(raw.replace(b'model = "gpt-5.6-luna"', b'model = "wrong"'))
        with patch.object(installer, "PROFILE_DIR", source):
            self.assert_install_error("HW_AGENT_SOURCE_INVALID")
        self.assertFalse((self.root / ".codex").exists())

    def test_source_profiles_reject_casefolded_hwahap_extras(self) -> None:
        source = self.root / "case-variant-source"
        source.mkdir()
        for path, raw in installer.source_profiles():
            (source / path.name).write_bytes(raw)
        (source / "user-agent.toml").write_bytes(b"name = 'unrelated'\n")
        for name in ("HWAHAP-extra.toml", "HWAHAP-extra.TOML"):
            (source / name).write_bytes(b"name = 'extra'\n")
            with self.assertRaises(installer.InstallError) as raised:
                installer.source_profiles(source)
            self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
            with patch.object(installer, "PROFILE_DIR", source):
                self.assert_install_error("HW_AGENT_SOURCE_INVALID")
            self.assertFalse((self.root / ".codex").exists())
            (source / name).unlink()
        self.assertEqual({path.name for path, _ in installer.source_profiles(source)}, installer.REQUIRED_PROFILE_NAMES)

    def test_source_directory_read_error_and_cli_install_error_are_generic(self) -> None:
        marker = "Authorization: Bearer /private/tmp/source-canary"
        with patch.object(Path, "iterdir", side_effect=OSError(marker)):
            with self.assertRaises(installer.InstallError) as raised:
                installer.source_profiles()
        self.assertEqual(raised.exception.code, "HW_AGENT_SOURCE_INVALID")
        self.assertNotIn(marker, str(raised.exception))
        stderr = io.StringIO()
        with patch.object(installer, "install", side_effect=OSError(marker)):
            with redirect_stderr(stderr):
                self.assertEqual(installer.main(["--workspace", str(self.root)]), 1)
        self.assertEqual(stderr.getvalue(), "HW_AGENT_INSTALL_FAILED: profile installation failed\n")
        self.assertNotIn(marker, stderr.getvalue())

    def test_unrelated_target_profile_is_preserved(self) -> None:
        self.install()
        unrelated = self.root / ".codex" / "agents" / "user-agent.toml"
        unrelated.write_text('name = "user-agent"\n', encoding="utf-8")
        self.install()
        self.assertEqual(unrelated.read_text(encoding="utf-8"), 'name = "user-agent"\n')

    def test_conflict_stops_without_mutation_or_later_installs(self) -> None:
        profiles = installer.source_profiles()
        agents = self.root / ".codex" / "agents"
        agents.mkdir(parents=True)
        first = agents / profiles[0][0].name
        original = b"different existing profile\n"
        first.write_bytes(original)
        self.assert_install_error("HW_AGENT_CONFLICT")
        self.assertEqual(first.read_bytes(), original)
        for path, _ in profiles[1:]:
            self.assertFalse((agents / path.name).exists())

    def test_preflight_conflict_does_not_create_any_pending_profile(self) -> None:
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("preflight-conflict")
        conflicting = workspace / ".codex" / "agents" / profiles[1][0].name
        conflicting.write_bytes(b"conflict-canary")
        with self.assertRaises(installer.InstallError) as raised:
            self.install(workspace)
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
        self.assertEqual(conflicting.read_bytes(), b"conflict-canary")
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
        for path, _ in profiles[2:]:
            self.assertFalse((workspace / ".codex" / "agents" / path.name).exists())

    def test_unexpected_hwahap_profile_is_rejected_before_any_write(self) -> None:
        for index, name in enumerate(("hwahap-extra.toml", "HWAHAP-extra.TOML")):
            with self.subTest(name=name):
                workspace = self.root / f"unexpected-{index}"
                agents = workspace / ".codex" / "agents"
                agents.mkdir(parents=True)
                marker = agents / name
                marker.write_bytes(b"credential-canary")
                unrelated = agents / "user-agent.toml"
                unrelated.write_bytes(b"unrelated")
                config = workspace / ".codex" / "config.toml"
                config.write_bytes(b"[project]\nname='keep'\n")
                with self.assertRaises(installer.InstallError) as raised:
                    self.install(workspace)
                self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
                self.assertNotIn(name, str(raised.exception))
                self.assertNotIn(str(workspace), str(raised.exception))
                self.assertEqual(marker.read_bytes(), b"credential-canary")
                self.assertEqual(unrelated.read_bytes(), b"unrelated")
                self.assertEqual(config.read_bytes(), b"[project]\nname='keep'\n")
                self.assertFalse(any((agents / path.name).exists() for path, _ in installer.source_profiles()))

    def test_write_failures_rollback_all_new_profiles(self) -> None:
        for index in (2, 3, 4):
            with self.subTest(index=index):
                workspace, profiles, unrelated, config = self.prepare_partial_workspace(f"write-failure-{index}")
                with self.assertRaises(installer.InstallError) as raised:
                    self.install_with_open_failure(workspace, profiles, index, "write")
                self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
                self.assertNotIn("canary", str(raised.exception))
                self.assertNotIn(str(workspace), str(raised.exception))
                agents = workspace / ".codex" / "agents"
                self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
                self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
                self.assertEqual((agents / profiles[0][0].name).read_bytes(), profiles[0][1])
                for path, _ in profiles[1:]:
                    self.assertFalse((agents / path.name).exists())

    def test_close_failure_and_cleanup_failure_are_stable(self) -> None:
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("close-failure")
        with self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 2, "close")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertNotIn("canary", str(raised.exception))
        agents = workspace / ".codex" / "agents"
        self.assertFalse((agents / profiles[1][0].name).exists())
        self.assertFalse((agents / profiles[2][0].name).exists())
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

        workspace, profiles, unrelated, config = self.prepare_partial_workspace("cleanup-failure")
        failing_target = workspace / ".codex" / "agents" / profiles[1][0].name
        original_unlink = installer.os.unlink

        def fail_one_unlink(name, *args, **kwargs):
            if name == failing_target.name:
                raise OSError("unlink-canary")
            return original_unlink(name, *args, **kwargs)

        with patch.object(installer.os, "unlink", new=fail_one_unlink):
            with self.assertRaises(installer.InstallError) as raised:
                self.install_with_open_failure(workspace, profiles, 2, "write")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation failed; rollback incomplete")
        self.assertNotIn("canary", str(raised.exception))
        self.assertTrue(failing_target.exists())
        self.assertEqual((workspace / ".codex" / "agents" / profiles[0][0].name).read_bytes(), profiles[0][1])
        self.assertFalse((workspace / ".codex" / "agents" / profiles[2][0].name).exists())
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

    def test_file_exists_race_preserves_racing_target(self) -> None:
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("file-exists-race")
        racing = workspace / ".codex" / "agents" / profiles[1][0].name
        with self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 1, "race")
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
        self.assertNotIn("race-canary", str(raised.exception))
        self.assertEqual(racing.read_bytes(), b"race-canary")
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
        for path, _ in profiles[2:]:
            self.assertFalse((workspace / ".codex" / "agents" / path.name).exists())

        for index in (2, 3):
            with self.subTest(index=index):
                workspace, profiles, unrelated, config = self.prepare_partial_workspace(f"file-exists-race-{index}")
                racing = workspace / ".codex" / "agents" / profiles[index][0].name
                with self.assertRaises(installer.InstallError) as raised:
                    self.install_with_open_failure(workspace, profiles, index, "race")
                self.assertEqual(raised.exception.code, "HW_AGENT_CONFLICT")
                self.assertNotIn("race-canary", str(raised.exception))
                self.assertEqual(racing.read_bytes(), b"race-canary")
                self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
                self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)
                for path, _ in profiles[1:]:
                    if path.name != racing.name:
                        self.assertFalse((workspace / ".codex" / "agents" / path.name).exists())

    def test_file_exists_race_with_incomplete_rollback_is_stable(self) -> None:
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("race-rollback-failure")
        prior = workspace / ".codex" / "agents" / profiles[1][0].name
        original_unlink = installer.os.unlink
        def fail_prior(name, *args, **kwargs):
            if name == prior.name:
                raise OSError("unlink-canary")
            return original_unlink(name, *args, **kwargs)
        with patch.object(installer.os, "unlink", new=fail_prior):
            with self.assertRaises(installer.InstallError) as raised:
                self.install_with_open_failure(workspace, profiles, 2, "race")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation conflict; rollback incomplete")
        self.assertTrue(prior.exists())
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

    def test_race_replacement_is_not_deleted(self) -> None:
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("race-replacement")
        prior = workspace / ".codex" / "agents" / profiles[1][0].name
        racing = workspace / ".codex" / "agents" / profiles[2][0].name
        with self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 2, "race-replace")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation conflict; rollback incomplete")
        self.assertEqual(prior.read_bytes(), b"replacement-canary")
        self.assertEqual(racing.read_bytes(), b"race-canary")
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

    def test_write_failure_replacement_is_not_deleted(self) -> None:
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("write-replacement")
        prior = workspace / ".codex" / "agents" / profiles[1][0].name
        with self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 2, "write-replace")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation failed; rollback incomplete")
        self.assertEqual(prior.read_bytes(), b"replacement-canary")
        self.assertFalse((workspace / ".codex" / "agents" / profiles[2][0].name).exists())
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

    def test_directory_replacement_uses_original_descriptors(self) -> None:
        profiles = installer.source_profiles()
        for component in ("codex", "agents"):
            for fail_index in (1, 2):
                with self.subTest(component=component, fail_index=fail_index):
                    workspace = self.root / f"swap-{component}-{fail_index}"
                    agents = workspace / ".codex" / "agents"
                    agents.mkdir(parents=True)
                    external = workspace / f"external-{component}-{fail_index}"
                    external.mkdir()
                    original_os_open = installer.os.open
                    calls = 0

                    def open_with_swap(name, flags, mode=0o777, *, dir_fd=None):
                        nonlocal calls
                        if flags & os.O_CREAT and flags & os.O_EXCL:
                            calls += 1
                            if calls == fail_index:
                                original = workspace / ".codex" / ("agents" if component == "agents" else "")
                                moved = workspace / f"{component}-original"
                                original.rename(moved)
                                original.symlink_to(external, target_is_directory=True)
                        return original_os_open(name, flags, mode, dir_fd=dir_fd)

                    with patch.object(installer.os, "open", new=open_with_swap):
                        with self.assertRaises(installer.InstallError) as raised:
                            self.install(workspace)
                    self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
                    self.assertNotIn(str(workspace), str(raised.exception))
                    self.assertEqual(list(external.iterdir()), [])
                    visible = workspace / ".codex" / ("agents" if component == "agents" else "")
                    self.assertTrue(visible.is_symlink())
                    original_agents = (workspace / "agents-original" if component == "agents"
                                       else workspace / "codex-original" / "agents")
                    for path, _ in profiles:
                        self.assertFalse((original_agents / path.name).exists())

    def test_late_unexpected_profile_rolls_back_and_normalizes_error(self) -> None:
        workspace, profiles, unrelated, config = self.prepare_partial_workspace("late-extra")
        failing = workspace / ".codex" / "agents" / profiles[1][0].name
        original_unlink = installer.os.unlink

        def fail_one(name, *args, **kwargs):
            if name == failing.name:
                raise OSError("unlink-canary")
            return original_unlink(name, *args, **kwargs)

        with patch.object(installer.os, "unlink", new=fail_one), self.assertRaises(installer.InstallError) as raised:
            self.install_with_open_failure(workspace, profiles, 4, "late-extra")
        self.assertEqual(raised.exception.code, "HW_AGENT_INSTALL_FAILED")
        self.assertEqual(str(raised.exception), "profile installation conflict; rollback incomplete")
        self.assertTrue(failing.exists())
        self.assertEqual((workspace / ".codex" / "agents" / "hwahap-extra.toml").read_bytes(), b"extra-canary")
        self.assertEqual(unrelated.read_bytes(), b"name = 'unrelated'\n")
        self.assertEqual((workspace / ".codex" / "config.toml").read_bytes(), config)

    def test_symlinked_state_paths_fail_closed(self) -> None:
        for name in ("codex", "agents", "target"):
            with self.subTest(path=name):
                workspace = self.root / name
                workspace.mkdir()
                if name == "codex":
                    target = workspace / "codex-target"
                    target.mkdir()
                    (workspace / ".codex").symlink_to(target, target_is_directory=True)
                else:
                    codex = workspace / ".codex"
                    codex.mkdir()
                    target = workspace / f"{name}-target"
                    target.mkdir()
                    agents = codex / "agents"
                    if name == "agents":
                        agents.symlink_to(target, target_is_directory=True)
                    else:
                        agents.mkdir()
                        profile = installer.source_profiles()[0][0].name
                        target_file = workspace / "profile-target"
                        target_file.write_bytes(b"existing")
                        (agents / profile).symlink_to(target_file)
                self.assert_install_error("HW_AGENT_PATH_INVALID", workspace)

    def test_missing_or_non_directory_workspace_fails(self) -> None:
        self.assert_install_error("HW_AGENT_PATH_INVALID", self.root / "missing")
        file_path = self.root / "workspace-file"
        file_path.write_text("not a directory", encoding="utf-8")
        self.assert_install_error("HW_AGENT_PATH_INVALID", file_path)

    def test_symlink_workspace_fails_before_resolve(self) -> None:
        target = self.root / "real-workspace"
        target.mkdir()
        link = self.root / "workspace-link"
        link.symlink_to(target, target_is_directory=True)
        self.assert_install_error("HW_AGENT_PATH_INVALID", link)
        self.assertFalse((target / ".codex").exists())

    def test_ancestor_symlink_workspace_fails_without_creating_state(self) -> None:
        target_parent = self.root / "target-parent"
        target_parent.mkdir()
        (target_parent / "project").mkdir()
        alias_parent = self.root / "alias-parent"
        alias_parent.symlink_to(target_parent, target_is_directory=True)
        workspace = alias_parent / "project"
        self.assert_install_error("HW_AGENT_PATH_INVALID", workspace)
        self.assertFalse((target_parent / "project" / ".codex").exists())

    def test_installer_never_creates_or_edits_config_toml(self) -> None:
        self.install()
        self.assertFalse((self.root / ".codex" / "config.toml").exists())
        existing = self.root / "with-config"
        (existing / ".codex").mkdir(parents=True)
        config = existing / ".codex" / "config.toml"
        original = b"[project]\nname = 'user-config'\n"
        config.write_bytes(original)
        self.install(existing)
        self.assertEqual(config.read_bytes(), original)

    def test_public_cli_errors_are_static_and_path_free(self) -> None:
        self.assertEqual(set(installer.PUBLIC_ERROR_MESSAGES), {
            "HW_AGENT_ARGUMENT_INVALID", "HW_AGENT_SOURCE_INVALID", "HW_AGENT_PATH_INVALID",
            "HW_AGENT_CONFLICT", "HW_AGENT_CONFIG_INVALID", "HW_AGENT_INSTALL_FAILED"})
        marker = "Proxy-Authorization: Basic /private/tmp/installer-canary"
        for argv in (["--unknown", marker], []):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(installer.main(argv), 1)
            self.assertEqual(stderr.getvalue(), "HW_AGENT_ARGUMENT_INVALID: invalid installer arguments\n")
            self.assertNotIn(marker, stderr.getvalue())
        with patch.object(installer, "install", side_effect=OSError(marker)):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(installer.main(["--workspace", marker]), 1)
        self.assertEqual(stderr.getvalue(), "HW_AGENT_INSTALL_FAILED: profile installation failed\n")
        self.assertNotIn(marker, stderr.getvalue())

    def test_symlink_path_error_does_not_echo_workspace(self) -> None:
        target = self.root / "real"
        target.mkdir()
        link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(installer.InstallError) as raised:
            installer.install(str(link))
        self.assertEqual(raised.exception.code, "HW_AGENT_PATH_INVALID")
        self.assertNotIn(str(link), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
