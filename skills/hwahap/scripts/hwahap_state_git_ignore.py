"""Verify that the private Hwahap state is excluded by Git."""
from __future__ import annotations
from hwahap_state_runtime import *
import hwahap_state_process
register(globals())


def _require_hwahap_ignored(workspace: Path) -> None:
    git_executable = shutil.which("git", path=os.defpath)
    if not git_executable or Path(git_executable).is_symlink() or not Path(git_executable).is_file():
        return
    env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull, "GIT_ATTR_NOSYSTEM": "1", "LC_ALL": "C", "LANG": "C"}
    try:
        inside = subprocess.run([git_executable, "rev-parse", "--is-inside-work-tree"], cwd=workspace,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=False)
        if inside.returncode != 0:
            return
        ignored = subprocess.run([git_executable, "check-ignore", "-q", "--no-index", "--", ".hwahap/probe"],
                                 cwd=workspace, env=env, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HwahapError("HW_STATE_INVALID", "could not verify .hwahap ignore policy") from exc
    if ignored.returncode != 0:
        raise HwahapError("HW_STATE_INVALID", ".hwahap must be excluded by Git ignore policy")
