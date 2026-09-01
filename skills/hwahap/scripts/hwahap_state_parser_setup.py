"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _command(commands, name: str, help_text: str, handler, arguments):
    command = commands.add_parser(name, help=help_text)
    for flags, options in arguments:
        command.add_argument(*flags, **options)
    command.set_defaults(handler=handler)
    return command


def _parser_setup(commands) -> None:
    required = lambda name: ((f"--{name}",), {"required": True})
    _command(commands, "init", "initialize a run from an approved PR/FAQ", init_run,
             [required("workspace"), required("goal-id"), required("spec")])
    _command(commands, "init-request", "initialize a run from a confirmed implementation request",
             init_run, [required("workspace"), required("goal-id"), required("request")])
    _command(commands, "init-goal", "initialize a run from a handoff-ready align-goal artifact",
             init_run, [required("workspace"), required("goal-id"), required("goal-spec")])
    common = [required("workspace"), required("run-id")]
    _command(commands, "lock", "lock a filled contract and record its first transition",
             lock_contract, common + [required("actor"), required("reason"),
                                      (("--evidence-ref",), {"action": "append", "required": True})])
    _command(commands, "add-unit", "add one planned atomic unit", add_unit, common + [
        required("unit-id"), required("title"),
        (("--source-unit-id",), {}),
        (("--allowed-path",), {"action": "append", "required": True}),
        (("--acceptance-command",), {"action": "append", "required": True})])
    test = _command(commands, "run-test", "compatibility command; test execution is disabled",
                    run_test, common + [required("unit-id"),
                    (("--command-index",), {"type": int, "required": True}),
                    (("--timeout-seconds",), {"type": int, "required": True})])
    test.description = "Compatibility command only; execution is disabled and no process is created."
    receipt = _command(commands, "record-test-receipt",
        "record an external acceptance test receipt", record_test_receipt, common + [
        required("unit-id"), (("--command-index",), {"type": int, "required": True}),
        required("execution-receipt-sha256"), required("observer-thread-id"),
        required("diff-digest"), required("base-commit"), required("target-commit"),
        required("started-at"), required("ended-at"), required("output-sha256")])
    outcome = receipt.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--exit-code", type=int)
    outcome.add_argument("--timed-out", action="store_true")
