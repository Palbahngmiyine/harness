try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_statekit_02 import *
    from .test_statekit_03 import *
    from .test_statekit_04 import *
    from .test_statekit_05 import *
    from .test_statekit_06 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_statekit_02 import *
    from test_statekit_03 import *
    from test_statekit_04 import *
    from test_statekit_05 import *
    from test_statekit_06 import *

class HwahapStateTests(StateFixtureMixin01, StateFixtureMixin02, StateFixtureMixin03, StateFixtureMixin04, StateFixtureMixin05, StateFixtureMixin06, unittest.TestCase):
        def test_authorization_header_variants_are_rejected_without_write_or_echo(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            base = json.loads(run_path.read_text())
            variants = (
                "Authorization: Basic state-basic-secret",
                "Authorization: Digest state-digest-secret",
                'Authorization: Digest username="state-user", realm="state-realm", response="state-response"',
                "Authorization: Basic state-lf-secret\nnext-line",
                "Proxy-Authorization: Basic state-crlf-secret\r\nnext-line",
                'Authorization: Digest username="state-fold-user"\r\n  realm="state-fold-realm"\r\n\tresponse="state-fold-response"',
                "Authorization: Basic [redacted]\r\n\tusername=state-basic-redacted-fold-secret",
                "Authorization: Digest [redacted]\n  username=state-digest-redacted-fold-secret",
                "Proxy-Authorization: Basic [redacted]\r\n\tproxy=state-proxy-redacted-fold-secret",
                "Proxy-Authorization: Bearer state-proxy-bearer-secret",
                "Proxy-Authorization: Basic state-proxy-basic-secret",
                "Proxy-Authorization: Digest state-proxy-digest-secret",
                "X-Api-Key: state-api-key-secret",
                "Authorization: Basic [redacted] state-redacted-tail-secret",
                "Authorization: Digest [redacted] state-digest-redacted-tail-secret",
                "Proxy-Authorization: Digest [redacted] state-proxy-redacted-tail-secret",
                "Authorization: Basic state-prefix-secret [redacted]",
                "Authorization: Digest state-digest-prefix-secret [redacted]",
                "Proxy-Authorization: Digest state-proxy-prefix-secret [redacted]",
                "Authorization: Basic state-basic-cr-secret\rnext-line",
                "Authorization: Digest state-digest-cr-secret\r\tresponse=state-digest-cr-folded",
                "Authorization: Bearer state-bearer-cr-secret\rnext-line",
                "Proxy-Authorization: Basic state-proxy-basic-cr-secret\rnext-line",
                "Proxy-Authorization: Digest state-proxy-digest-cr-secret\r\tresponse=state-proxy-digest-cr-folded",
                "Proxy-Authorization: Bearer state-proxy-bearer-cr-secret\rnext-line",
                "Authorization: Basic [redacted]\rresponse=state-basic-redacted-cr-sentinel",
                "Authorization: Digest [redacted]\rresponse=state-digest-redacted-cr-sentinel",
                "Authorization: Bearer [redacted]\rresponse=state-bearer-redacted-cr-sentinel",
                "Proxy-Authorization: Basic [redacted]\rresponse=state-proxy-basic-redacted-cr-sentinel",
                "Proxy-Authorization: Digest [redacted]\rresponse=state-proxy-digest-redacted-cr-sentinel",
                "Proxy-Authorization: Bearer [redacted]\rresponse=state-proxy-bearer-redacted-cr-sentinel",
            )
            for safe in ("Authorization: Basic [redacted]", "Authorization: Digest [redacted]",
                         "Proxy-Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                         "Authorization: Bearer [redacted]", "Proxy-Authorization: Bearer [redacted]"):
                self.assertFalse(hwahap_state.credential_bearing_text(safe))
            self.assertFalse(hwahap_state.credential_bearing_text("Authorization: Basic [redacted]\nnext-line"))
            for value in variants:
                with self.subTest(value=value):
                    run = copy.deepcopy(base)
                    run["goal_link"]["current"]["reason"] = value
                    run["goal_link"]["current"]["evidence"] = [value]
                    self.write_json(run_path, run)
                    before = {path: path.read_bytes() for path in (run_dir / "contract.json", run_path, run_dir / "events.jsonl")}
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        self.validate()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn(value, str(raised.exception))
                    for token in value.replace('"', '').split():
                        if token not in {"Authorization:", "Proxy-Authorization:", "Basic", "Digest", "Bearer", "next-line"}:
                            self.assertNotIn(token, str(raised.exception))
                    self.assertEqual({path: path.read_bytes() for path in before}, before)
