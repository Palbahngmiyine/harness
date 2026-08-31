import os
from pathlib import Path
from unittest.mock import patch

try:
    from .test_installerkit import InstallerFixture, installer
except ImportError:
    from test_installerkit import InstallerFixture, installer


class InstallerFaultMixin(InstallerFixture):
    def prepare_partial_workspace(self, name):
        workspace = self.root / name
        agents = workspace / ".codex" / "agents"
        agents.mkdir(parents=True)
        profiles = installer.source_profiles()
        (agents / profiles[0][0].name).write_bytes(profiles[0][1])
        unrelated = agents / "user-agent.toml"
        unrelated.write_bytes(b"name = 'unrelated'\n")
        config = workspace / ".codex" / "config.toml"
        config.write_bytes(b"[project]\nname = 'preserve'\n")
        return workspace, profiles, unrelated, config.read_bytes()

    def install_with_open_failure(self, workspace, profiles, fail_index, failure):
        original_open = Path.open
        original_os_open = installer.os.open
        original_fdopen = installer.os.fdopen
        agents = workspace / ".codex" / "agents"
        calls, faulty_fd = 0, -1

        class FaultyHandle:
            def __init__(self, handle): self.handle = handle
            def __enter__(self): self.handle.__enter__(); return self
            def __exit__(self, *args):
                result = self.handle.__exit__(*args)
                if failure == "write-replace" and args[0] is not None:
                    prior = agents / profiles[1][0].name
                    os.unlink(prior)
                    with original_open(prior, "wb") as replacement:
                        replacement.write(b"replacement-canary")
                if failure == "close" and args[0] is None:
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
                with original_open(agents / name, "wb") as handle:
                    handle.write(b"race-canary")
                raise FileExistsError("race-canary")
            if calls == fail_index and failure == "race-replace":
                prior = agents / profiles[1][0].name
                os.unlink(prior)
                with original_open(prior, "wb") as handle: handle.write(b"replacement-canary")
                with original_open(agents / name, "wb") as handle: handle.write(b"race-canary")
                raise FileExistsError("race-canary")
            fd = original_os_open(name, flags, mode, dir_fd=dir_fd)
            if calls == fail_index: faulty_fd = fd
            return fd

        def fdopen_with_failure(fd, *args, **kwargs):
            handle = original_fdopen(fd, *args, **kwargs)
            return FaultyHandle(handle) if fd == faulty_fd else handle

        with patch.object(installer, "source_profiles", return_value=profiles), \
                patch.object(installer.os, "open", new=open_with_failure), \
                patch.object(installer.os, "fdopen", new=fdopen_with_failure):
            installer.install(str(workspace))
