# Passive retry policy and loaded calendar boundary

Policy-only changes of `activate_evening` for the same drawing, runner version
and operational cutoff preserve every attempt timestamp and the hard-stop
timestamp. Only the activation flags and signed plan hash change. This is
intentional: a nonterminal retry child must not unload its own launchd job.
The next invocation reads the updated plan; persisted executed timestamps keep
already completed attempts from running twice.

This preserves the original retry cadence rather than switching between
bootstrap and normal cadences mid-plan. A tighter cutoff or runner upgrade
still requires regenerated artifacts; this slice does not add automatic
calendar reload inside a running child.

Installation validates the plan and generated wrapper/plist hashes before any
launchctl call, rejects foreign installed wrapper ownership, and refuses to
replace an existing loaded job without its installed owner file. An actual
calendar replacement is allowed only after launchctl explicitly reports
`state = not running` with no positive PID. Running or unrecognized state fails
before bootout. An absent loaded job can be restored once; unchanged loaded
bytes need no bootstrap.

A nonzero bootstrap result or inactive verification invokes exact-label cleanup.
After successful cleanup, prior installed plist bytes are restored but the job
is left unloaded: old schedules are not silently reactivated against a newer
plan. Cleanup errors remain errors; restoration is not claimed when cleanup
cannot establish removal. No transaction guarantee is made for OS/process
crashes or independent concurrent launchctl actors.

Cleanup distinguishes a loaded job (print exit 0), the established service-not-found
result (113), and unknown query failure. Any other/missing exit status propagates
an error before plist deletion. A successful bootout still requires a confirming
service-not-found query. Unknown state never authorizes restoration of old bytes.

Implementation and synthetic verification live only in the review worktree
until separately reviewed and explicitly integrated. No real launchctl,
production runtime, database or wagering action is part of this change.
