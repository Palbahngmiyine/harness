"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
class HwahapError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HwahapError("HW_STATE_INVALID", "invalid command arguments")


def git_diff_snapshot(workspace: Path, base_commit: object, target_commit: object) -> dict:
    if (not isinstance(base_commit, str) or not GIT_COMMIT.fullmatch(base_commit)
            or not isinstance(target_commit, str) or not GIT_COMMIT.fullmatch(target_commit)):
        raise HwahapError("HW_STATE_INVALID", "invalid Git diff snapshot commits")

    git_executable = shutil.which("git", path=os.defpath)
    if (not git_executable or Path(git_executable).is_symlink()
            or not Path(git_executable).is_file()):
        raise HwahapError("HW_STATE_INVALID", "trusted Git executable is unavailable")
    env = {"PATH": os.defpath}
    env.update({"GIT_NO_REPLACE_OBJECTS": "1", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_ATTR_NOSYSTEM": "1", "LC_ALL": "C", "LANG": "C"})

    def git(args: list[str]) -> bytes:
        try:
            return subprocess.run([git_executable, *args], cwd=workspace, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, check=True, env=env).stdout
        except Exception as exc:
            raise HwahapError("HW_STATE_INVALID", "could not resolve Git diff snapshot") from exc

    try:
        top = git(["rev-parse", "--show-toplevel"]).decode("utf-8").strip()
        git_dir = git(["rev-parse", "--absolute-git-dir"]).decode("utf-8").strip()
        if Path(top).resolve() != workspace.resolve() or not Path(git_dir).is_dir():
            raise ValueError
        base = git(["rev-parse", "--verify", f"{base_commit}^{{commit}}"]).decode("ascii").strip()
        target = git(["rev-parse", "--verify", f"{target_commit}^{{commit}}"]).decode("ascii").strip()
        if base != base_commit or target != target_commit:
            raise ValueError
        base_tree = git(["rev-parse", "--verify", f"{base_commit}^{{tree}}"]).decode("ascii").strip()
        target_tree = git(["rev-parse", "--verify", f"{target_commit}^{{tree}}"]).decode("ascii").strip()
        diff = git(["diff", "--full-index", "--binary", "--no-ext-diff", "--no-textconv", "--no-color",
                    "--diff-algorithm=myers", "--no-indent-heuristic", "--unified=3", "--src-prefix=a/",
                    "--dst-prefix=b/", "--no-renames", base_commit, target_commit, "--"])
        raw_paths = git(["diff", "--name-only", "-z", "--no-renames", base_commit, target_commit, "--"])
        paths = raw_paths.decode("utf-8").split("\0")
        if paths and paths[-1] == "":
            paths.pop()
        if (not GIT_COMMIT.fullmatch(base_tree) or not GIT_COMMIT.fullmatch(target_tree)
                or not paths or any(not safe_relative_path(path) for path in paths)):
            raise ValueError
    except HwahapError:
        raise
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "invalid Git diff snapshot") from exc
    return {"base_commit": base_commit, "target_commit": target_commit,
            "base_tree": base_tree, "target_tree": target_tree,
            "diff_digest": "sha256:" + hashlib.sha256(diff).hexdigest(),
            "changed_paths": paths}


def validate_diff_snapshot(value: object, workspace: Path | None, label: str, errors: list[str]) -> dict | None:
    if not isinstance(value, dict) or set(value) != DIFF_SNAPSHOT_FIELDS:
        errors.append(f"{label} is incomplete")
        return None
    if (not isinstance(value.get("base_commit"), str) or not GIT_COMMIT.fullmatch(value["base_commit"])
            or not isinstance(value.get("target_commit"), str) or not GIT_COMMIT.fullmatch(value["target_commit"])
            or not isinstance(value.get("base_tree"), str) or not GIT_COMMIT.fullmatch(value["base_tree"])
            or not isinstance(value.get("target_tree"), str) or not GIT_COMMIT.fullmatch(value["target_tree"])
            or not isinstance(value.get("diff_digest"), str) or not SHA256.fullmatch(value["diff_digest"])
            or not isinstance(value.get("changed_paths"), list) or not value["changed_paths"]
            or any(not isinstance(path, str) or not safe_relative_path(path) for path in value["changed_paths"])):
        errors.append(f"{label} is invalid")
        return None
    if workspace is None:
        return value
    try:
        actual = git_diff_snapshot(workspace, value["base_commit"], value["target_commit"])
    except HwahapError:
        errors.append(f"{label} cannot be resolved")
        return None
    if actual != value:
        errors.append(f"{label} does not match the current Git diff")
        return None
    return actual
