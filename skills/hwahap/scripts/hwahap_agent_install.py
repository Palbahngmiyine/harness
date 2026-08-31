"""Install validated profiles with descriptor-bound, race-safe rollback."""

import hashlib
import os
import stat
from pathlib import Path

from hwahap_agent_contract import InstallError
from hwahap_agent_io import (PF, assert_bound, cleanup, file_id, open_dir,
                             read_profile, reject_extras)
from hwahap_agent_profiles import lexical_path_has_symlink


def install_profiles(workspace_arg, profiles):
    path = Path(workspace_arg).expanduser()
    if lexical_path_has_symlink(path):
        raise InstallError("HW_AGENT_PATH_INVALID", "workspace must use real path components")
    workspace = path.resolve()
    if not workspace.is_dir():
        raise InstallError("HW_AGENT_PATH_INVALID", "workspace must be a non-symlink directory")
    wf = cf = af = -1
    created, installed, skipped = [], [], []
    try:
        wf = open_dir(None, workspace)
        cf = open_dir(wf, ".codex", True)
        af = open_dir(cf, "agents", True)
        ci, ai = file_id(os.fstat(cf)), file_id(os.fstat(af))
        reject_extras(af)
        pending = []
        for source, raw in profiles:
            try: info = os.stat(source.name, dir_fd=af, follow_symlinks=False)
            except FileNotFoundError: pending.append((source, raw)); continue
            except OSError as exc: raise InstallError("HW_AGENT_PATH_INVALID", "target must be a regular file") from exc
            if not stat.S_ISREG(info.st_mode): raise InstallError("HW_AGENT_PATH_INVALID", "target must be a regular file")
            if read_profile(af, source.name) == raw: skipped.append(source.name); continue
            raise InstallError("HW_AGENT_CONFLICT", "different existing profile")
        for source, raw in pending:
            assert_bound(wf, cf, ci, ai); reject_extras(af)
            handle = os.open(source.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=af)
            record = [source.name, os.dup(handle), hashlib.sha256(raw).hexdigest()]
            created.append(record)
            try:
                if not stat.S_ISREG(os.fstat(handle).st_mode): raise OSError("created profile is not regular")
                with os.fdopen(handle, "wb") as output: output.write(raw)
            except Exception:
                # A failed open/write still owns this inode.  Let rollback
                # remove it only while the descriptor identity remains bound.
                record[2] = None
                try: os.close(handle)
                except OSError: pass
                raise
            installed.append(source.name)
        assert_bound(wf, cf, ci, ai); reject_extras(af)
    except FileExistsError as exc:
        complete = not created or cleanup(af, created)
        code = "HW_AGENT_CONFLICT" if complete else "HW_AGENT_INSTALL_FAILED"
        msg = "profile installation conflict" if complete else "profile installation conflict; rollback incomplete"
        raise InstallError(code, msg) from exc
    except Exception as exc:
        complete = not created or (af >= 0 and cleanup(af, created))
        if isinstance(exc, InstallError) and complete: raise
        msg = "profile installation failed" if complete else "profile installation failed; rollback incomplete"
        if isinstance(exc, InstallError) and exc.code == "HW_AGENT_CONFLICT": msg = "profile installation conflict; rollback incomplete"
        raise InstallError("HW_AGENT_INSTALL_FAILED", msg) from exc
    finally:
        for _, guard, _ in created:
            if guard is not None:
                try: os.close(guard)
                except OSError: pass
        for handle in (af, cf, wf):
            if handle >= 0:
                try: os.close(handle)
                except OSError: pass
    print(f"HW_OK: installed={len(installed)} skipped={len(skipped)} target={workspace / '.codex' / 'agents'}")
