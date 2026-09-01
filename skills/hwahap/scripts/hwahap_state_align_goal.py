"""Read and bind one align-goal/v1 implementation handoff."""
from __future__ import annotations
from hwahap_state_runtime import *
import unicodedata
register(globals())
ALIGN_PROJECTION_KEYS = ("contract_version", "revision", "target", "goal", "facts",
    "choices", "question_rounds", "decision_surfaces", "specifications",
    "acceptance_checks", "implementation_units", "open_items")
ALIGN_TOP_KEYS = set(ALIGN_PROJECTION_KEYS) | {"repository_context", "reviews", "confirmations"}
ALIGN_FRONT_KEYS = {"schema", "title", "target", "session_status", "alignment_status",
                    "handoff_status", "revision", "created", "updated", "response_log"}
def align_normalize(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [align_normalize(item) for item in value]
    if isinstance(value, dict):
        return {align_normalize(key): align_normalize(item) for key, item in value.items()}
    return value
def align_digest(value: object) -> str:
    data = json.dumps(align_normalize(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()
def align_pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError
        value[key] = item
    return value
def align_fail() -> None:
    raise HwahapError("HW_HANDOFF_UNCONFIRMED",
                      "align-goal handoff is unavailable or invalid")
def align_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, re.DOTALL)
    if not match or credential_bearing_text(match.group(1)):
        align_fail()
    values = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            align_fail()
        key, item = line.split(":", 1); key, item = key.strip(), item.strip().strip('"\'')
        if key in values:
            align_fail()
        values[key] = item
    required = {"schema": "align-goal/v1", "target": "implementation",
        "session_status": "complete", "alignment_status": "aligned",
        "handoff_status": "ready"}
    if set(values) != ALIGN_FRONT_KEYS or any(values.get(key) != item
            for key, item in required.items()) or not values.get("title") \
            or not values.get("revision", "").isdigit():
        align_fail()
    return values
def init_input_selection(args) -> tuple[str, str, str, str]:
    if getattr(args, "goal_spec", None) is not None:
        return "goal_spec", args.goal_spec, "align-goal", "HW_HANDOFF_UNCONFIRMED"
    if getattr(args, "request", None) is not None:
        return "request", args.request, "request", "HW_REQUEST_UNCONFIRMED"
    return "spec", args.spec, "prfaq", "HW_SPEC_UNCONFIRMED"
def input_spec_record(meta: dict, source: str, digest: str) -> dict:
    record = {"source": source, "sha256": digest,
              "confirmed_at": meta["confirmed_at"], "status": meta["status"]}
    if "handoff" in meta:
        record["handoff"] = meta["handoff"]
    return record
def load_goal_spec(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8"); front = align_frontmatter(text)
        blocks = re.findall(r"(?ms)^```json align-goal-contract\n(.*?)\n```[ \t]*$", text)
        if len(blocks) != 1:
            align_fail()
        contract = json.loads(blocks[0], object_pairs_hook=align_pairs)
        if not isinstance(contract, dict) or set(contract) != ALIGN_TOP_KEYS \
                or contract.get("contract_version") != "align-goal/v1" \
                or contract.get("target") != "implementation" \
                or contract.get("revision") != int(front["revision"]):
            align_fail()
        projection = {key: contract[key] for key in ALIGN_PROJECTION_KEYS}
        digest = align_digest(projection); reviews = contract["reviews"]
        ambiguity, cold = reviews["ambiguity_auditor"], reviews["cold_consumer"]
        handoff = contract["confirmations"]["handoff_document"]
        if any(item.get("status") != "pass" or item.get("spec_digest") != digest
               for item in (ambiguity, cold)) or handoff.get("spec_digest") != digest \
                or not handoff.get("exact_response", "").startswith("CONFIRM HANDOFF:") \
                or handoff.get("ambiguity_receipt_digest") != align_digest(ambiguity) \
                or handoff.get("cold_receipt_digest") != align_digest(cold):
            align_fail()
        trace = align_goal_trace(contract, digest)
        trace["confirmation"] = {"confirmed_at": handoff["confirmed_at"],
            "response_hash": handoff["response_ref"]["hash"]}
        return {"title": front["title"], "status": "align-goal",
                "confirmed_at": handoff["confirmed_at"], "handoff": trace}
    except (OSError, UnicodeError, AttributeError, KeyError, TypeError, ValueError,
            json.JSONDecodeError):
        align_fail()
