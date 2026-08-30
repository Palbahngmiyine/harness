try:
    from .test_statekit_base import *
except ImportError:
    from test_statekit_base import *

class StateFixtureMixin01:
        def setUp(self) -> None:
            temp_root = "/private/tmp" if Path("/private/tmp").is_dir() else None
            self.tempdir = tempfile.TemporaryDirectory(dir=temp_root)
            self.workspace = Path(self.tempdir.name)
            self.spec = self.workspace / "spec.md"
            self.spec.write_text(
                "---\ntitle: Test goal\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n",
                encoding="utf-8",
            )
            self.install_agents(self.workspace)
            (self.workspace / "src").write_text("base\n", encoding="utf-8")
            def git(*args: str) -> str:
                return subprocess.run(["git", *args], cwd=self.workspace, check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Hwahap Test")
            git("add", "-A")
            git("commit", "-qm", "base")
            self.base_commit = git("rev-parse", "HEAD")
            (self.workspace / "src").write_text("target\n", encoding="utf-8")
            git("add", "src")
            git("commit", "-qm", "target")
            self.target_commit = git("rev-parse", "HEAD")
            self.snapshot = hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit)

        def tearDown(self) -> None:
            self.tempdir.cleanup()

        def init_run(self, goal_id: str = "test-goal") -> Path:
            args = Namespace(workspace=str(self.workspace), goal_id=goal_id, spec=str(self.spec))
            with redirect_stdout(io.StringIO()):
                hwahap_state.init_run(args)
            return self.workspace / ".hwahap" / "runs" / goal_id

        def install_agents(self, workspace: Path) -> None:
            with redirect_stdout(io.StringIO()):
                installer.install(str(workspace))

        def validate(self, goal_id: str = "test-goal") -> None:
            args = Namespace(workspace=str(self.workspace), run_id=goal_id)
            with redirect_stdout(io.StringIO()):
                hwahap_state.validate_run(args)

        def validate_at(self, workspace: Path, goal_id: str = "test-goal") -> None:
            args = Namespace(workspace=str(workspace), run_id=goal_id)
            with redirect_stdout(io.StringIO()):
                hwahap_state.validate_run(args)

        def write_json(self, path: Path, value: dict) -> None:
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

        def write_events(self, run_dir: Path, transitions: list[tuple[str, str, str]]) -> None:
            events = []
            for sequence, (entity, source, target) in enumerate(transitions, 1):
                events.append({
                    "timestamp": "2026-08-27T00:00:00Z", "type": "state_transition",
                    "sequence": sequence, "entity": entity, "from": source, "to": target,
                    "actor": "sol-1", "role": "orchestrator", "reason": "test transition",
                    "input_digest": "sha256:" + "a" * 64, "evidence_refs": ["test"], "review_round": 0,
                })
            (run_dir / "events.jsonl").write_text(
                "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
            )

        def bind_last_event_digest(self, run_dir: Path) -> None:
            path = run_dir / "events.jsonl"
            events = hwahap_state.parse_events(path)
            events[-1]["input_digest"] = self.snapshot["diff_digest"]
            path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

        @staticmethod
        def phase_events(unit_status: str = "reviewing", run_status: str | None = None) -> list[tuple[str, str, str]]:
            run_status = run_status or ("reviewing" if unit_status in {"reviewing", "passed"} else unit_status)
            events = [("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                      ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                      ("unit-1", "implementing", "reviewing")]
            if run_status == "recovering":
                events.append(("run", "reviewing", "recovering"))
            elif run_status == "replanning":
                events.append(("run", "reviewing", "replanning"))
            if unit_status != "reviewing":
                events.append(("unit-1", "reviewing", unit_status))
            return events
