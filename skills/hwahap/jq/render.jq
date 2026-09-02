# Render goal.json into the byte-stable align.md confirmation view.
def answer: if . == null then "UNANSWERED" else .text end;
def bullets($items): if ($items | length) == 0 then "- 없음"
  else $items | map("- " + .) | join("\n") end;
def choice:
  "### \(.id) · \(.kind) · \(.surface)\n\(.question)\n" +
  (.alternatives | map("- \(.id): \(.value)") | join("\n")) +
  "\n추천: \(.recommendation)\n답: \(.answer | answer)\n근거: \(.evidence | join(", "))";
def unit:
  "### \(.id) · \(.title)\npaths: \(.paths | join(", "))\n" +
  "test: \(.test)\nacceptance: \(.acceptance_ids | join(", "))\n" +
  "depends_on: \(.depends_on | join(", "))\nprobe: \(.probe)";

[
  "# hwahap align: \(.goal_id) (revision \(.revision))",
  "## Goal\n\(.goal.statement)",
  "## Success\n" + bullets(.goal.success),
  "## Non-goals\n" + bullets(.goal.non_goals),
  "## Surfaces",
  (.surfaces.applicable | sort | map("- \(.): applicable") | join("\n")),
  (.surfaces.not_applicable | to_entries | sort_by(.key) |
    map("- \(.key): NA · \(.value.reason) · \(.value.answer.text)") | join("\n")),
  "## Terms",
  (.terms | sort_by(.term) | map("- \(.term): \(.definition) [\(.choice_id)]") | join("\n")),
  "## Choices",
  (.choices | sort_by(.id) | map(choice) | join("\n\n")),
  "## Specs",
  (.specs | sort_by(.id) | map("- \(.id): \(.statement) [\(.choice_ids | join(", "))]") | join("\n")),
  "## Acceptance",
  (.acceptance | sort_by(.id) | map("- \(.id): \(.test) [\(.spec_ids | join(", "))]") | join("\n")),
  "## Units",
  (.units | sort_by(.id) | map(unit) | join("\n\n")),
  "## Probe results",
  (.units | map(select(.probe)) | map("- \(.id): .hwahap/out/\(.id).patch") | join("\n")),
  "## Open items\n" + (if any(.open_items[]; .status == "open") then
    (.open_items | map(select(.status == "open") | "- \(.id): \(.kind) [\(.choice_id)]") | join("\n")) else "- 없음" end)
] | map(select(length > 0)) | join("\n\n")
