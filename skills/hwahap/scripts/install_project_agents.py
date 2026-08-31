#!/usr/bin/env python3
"""Compatibility facade for the modular Hwahap project-agent installer."""

import os
import shutil
import sys
from pathlib import Path

try:
    from . import hwahap_agent_contract as contract
    from . import hwahap_agent_install as implementation
    from . import hwahap_agent_profiles as profiles
except ImportError:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path: sys.path.insert(0, script_dir)
    import hwahap_agent_contract as contract
    import hwahap_agent_install as implementation
    import hwahap_agent_profiles as profiles

PROFILE_DIR = contract.PROFILE_DIR
PROFILE_CONTRACT = contract.PROFILE_CONTRACT
PROFILE_SHA256 = contract.PROFILE_SHA256
REQUIRED_FIELDS = contract.REQUIRED_FIELDS
REQUIRED_PROFILE_NAMES = contract.REQUIRED_PROFILE_NAMES
PUBLIC_ERROR_MESSAGES = contract.PUBLIC_ERROR_MESSAGES
InstallError = contract.InstallError
SafeArgumentParser = contract.SafeArgumentParser
is_hwahap_profile_name = contract.is_hwahap_profile_name


def source_profiles(profile_dir=None):
    return profiles.source_profiles(profile_dir or PROFILE_DIR)


def install(workspace_arg):
    return implementation.install_profiles(workspace_arg, source_profiles())


def main(argv=None):
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--workspace")
    try:
        args = parser.parse_args(argv)
        if not args.workspace: raise InstallError("HW_AGENT_ARGUMENT_INVALID", "--workspace is required")
        install(args.workspace)
    except InstallError as exc:
        code = exc.code if exc.code in PUBLIC_ERROR_MESSAGES else "HW_AGENT_INSTALL_FAILED"
        print(f"{code}: {PUBLIC_ERROR_MESSAGES[code]}", file=sys.stderr)
        return 1
    except (OSError, shutil.Error):
        print("HW_AGENT_INSTALL_FAILED: profile installation failed", file=sys.stderr)
        return 1
    except Exception:
        print("HW_AGENT_INSTALL_FAILED: profile installation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__": raise SystemExit(main())
