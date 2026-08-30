"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def parser() -> argparse.ArgumentParser:
    root = SafeArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    _parser_setup(commands)
    _parser_workflow(commands)
    _parser_goal(commands)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        args.handler(args)
        return 0
    except HwahapError as exc:
        code = exc.code if exc.code in PUBLIC_ERROR_MESSAGES else "HW_STATE_INVALID"
        print(f"{code}: {PUBLIC_ERROR_MESSAGES[code]}", file=sys.stderr)
        return 1
    except Exception:
        print("HW_STATE_INVALID: command failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
