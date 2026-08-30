try:
    from .test_dependency_kit import *
except ImportError:
    from test_dependency_kit import *

class DependencySlice5Tests(DependencyIntegrityTests):
    def test_launcher_is_absolute_fixed_and_rejects_symlink_entrypoint(self) -> None:
            launcher = ROOT / "hwahap"
            source = launcher.read_text(encoding="utf-8")
            self.assertNotIn("dirname", source)
            self.assertNotIn("readlink", source)
            self.assertNotIn("which", source)
            self.assertNotIn("$(", source)
            self.assertIn("-I -S", source)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fake_path = root / "bin"
                fake_path.mkdir()
                for name in ("python3", "dirname"):
                    fake = fake_path / name
                    fake.write_text("printf '%s\\n' launcher-canary >&2; exit 1\n", encoding="utf-8")
                    fake.chmod(0o755)
                env = {"PATH": str(fake_path), "PYTHONPATH": str(root)}
                result = subprocess.run([str(launcher), "--help"], cwd=root, env=env,
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0)
                self.assertNotIn("launcher-canary", result.stdout + result.stderr)
                link = root / "launcher-link"
                link.symlink_to(launcher)
                linked = subprocess.run([str(link), "--help"], cwd=root, env=env,
                                        capture_output=True, text=True, check=False)
                self.assertEqual(linked.returncode, 1)
                self.assertEqual(linked.stderr, "HW_STATE_INVALID: state is invalid\n")
                self.assertNotIn(str(root), linked.stderr)

class DependencySlice6Tests(DependencyIntegrityTests):
    def test_official_commands_use_absolute_launcher_and_readme_help_runs(self) -> None:
            repository = ROOT.parents[2]
            documents = (
                repository / "skills/hwahap/SKILL.md",
                repository / "skills/hwahap/references/protocol.md",
                repository / "skills/hwahap/references/state-contract.md",
                repository / "skills/hwahap/assets/agents/hwahap-sol-orchestrator.toml",
            )
            marker = "<absolute-hwahap-skill-dir>/scripts/hwahap"
            for document in documents:
                for line in document.read_text(encoding="utf-8").splitlines():
                    if "scripts/hwahap" in line:
                        self.assertIn(marker, line, document.name)
            readme = (repository / "README.md").read_text(encoding="utf-8")
            self.assertIn('"$PWD/skills/hwahap/scripts/hwahap" --help', readme)
            launcher = (repository / "skills/hwahap/scripts/hwahap").resolve()
            result = subprocess.run(
                [str(launcher), "--help"], cwd=repository,
                env={"PATH": os.defpath}, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertIn("usage:", result.stdout.lower())
