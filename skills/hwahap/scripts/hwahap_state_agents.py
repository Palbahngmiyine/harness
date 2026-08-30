"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def verify_installed_agents(workspace: Path) -> dict[str, str]:
    _ensure_dependencies()
    agent = _dependency_modules[0]
    codex_dir = workspace / ".codex"
    target_dir = codex_dir / "agents"
    try:
        for path in (codex_dir, target_dir):
            if lexical_path_has_symlink(path) or path.is_symlink() or not path.is_dir():
                raise HwahapError("HW_AGENT_CONFIG_INVALID", "project agent directory is missing or unsafe")
    except HwahapError:
        raise
    except (OSError, UnicodeError) as exc:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "cannot inspect project agent directories") from exc
    try:
        profiles = agent.source_profiles(AGENT_PROFILE_DIR)
    except agent.InstallError as exc:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "Hwahap source profiles are invalid") from exc
    required_names = {source.name for source, _ in profiles}
    try:
        target_names = {
            path.name for path in target_dir.iterdir()
            if agent.is_hwahap_profile_name(path.name)
        }
    except (OSError, UnicodeError) as exc:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "cannot inspect installed Hwahap profiles") from exc
    if target_names != required_names:
        raise HwahapError("HW_AGENT_CONFIG_INVALID", "installed Hwahap profiles are not exactly the required set")
    hashes: dict[str, str] = {}
    for source, source_bytes in profiles:
        target = target_dir / source.name
        try:
            if source.is_symlink() or not source.is_file() or target.is_symlink() or not target.is_file():
                raise HwahapError("HW_AGENT_CONFIG_INVALID", "installed Hwahap profile is missing or unsafe")
            if target.read_bytes() != source_bytes:
                raise HwahapError("HW_AGENT_CONFIG_INVALID", "agent profile differs from Hwahap")
        except HwahapError:
            raise
        except (OSError, UnicodeError) as exc:
            raise HwahapError("HW_AGENT_CONFIG_INVALID", "cannot read installed Hwahap profile") from exc
        hashes[source.name] = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    return hashes
