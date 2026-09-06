# GOAL schedule collection: opt-in per-fixture quarantine

The default `GoalAPIClient.fetch_schedule` remains strict: any duplicate fixture
with differing protected semantic content raises. The accepted `updatedAt`-only
semantic equivalence rule is unchanged. Team-results parsing/filtering is unchanged.

`fetch_schedule_for_collection` is explicitly selected by the schedule candidate
collector. On a protected difference it quarantines that provider fixture ID for
the entire requested window. No version wins, later matching observations cannot
resurrect it, and pagination continues across pages/dates within existing request
budgets. Other individually valid, non-conflicting fixtures remain available only
after complete pagination. Latest observation selection for equivalent fixtures
remains conservative at kickoff; timestamps are not rewritten.

`GoalAPIScheduleConflict` retains every parsed observation and its immutable page
request evidence. Public diagnostics record all differing protected field names,
raw-event hashes, page/response hashes, actual fetch times, endpoint and request
fingerprints. Both full raws remain in the referenced original page snapshots;
no raw score value is ignored or reconstructed. Quarantine is never eligibility.

Candidate matching vetoes a target when any eligible quarantined observation
matches it (including reversed/name changes), or its explicit source fixture ID
is quarantined. Another convenient ID cannot replace that target. Independent
unrelated targets still use the existing matcher, timing, status and review gates.
Candidates remain ledger_eligible=false with official-source/review requirements.

Successful pagination with exclusions reports `partial_conflicts`,
`pagination_complete=true`, counts and full quarantine provenance. This is not
complete provider coverage. Budget, transport, schema or parsing failure still
raises and returns no partial candidate set; collector reports source_failed and
pagination_complete=false, retaining already observed conflict diagnostics.
This change does not selectively forgive malformed events or history conflicts.

Regression evidence uses exact raw observations from saved4998 GOAL offsets500/600:
two completed fixtures changed halftime nulls to populated scores. The portable
fixture retains original page/raw hashes and timestamps; its unit-test transport
is explicitly synthetic. Full seven-page offline replay separately proves
quarantine of both IDs and continuation to the genuinely missing offset700.
No missing pages, terminal pagination flags or current4998 mappings are invented.

This does not refresh the cached zero-coverage goal-auto marker, fetch histories,
change a pinned seed, authorize release or install jobs. Those are separate work.
No sports probability or profitability improvement is claimed.
