# P2 repeated-normalization fix

Task TOTOAI-RESUME-20260915. Completed 2026-09-15T18:50:39.016027+00:00. **IMPLEMENTED; pending independent Huygens review.**

- Fixed only P2-NORMALIZATION-REBIND. Public bind normalizes external probabilities once; private common binder validates frozen normalized tuples without mutating floats. Repair reuses this representation.
- Exact expected/stored/payload SHA checks retained. Unit-mass tolerance2ULP(1.0) is semantic validation only, not rounding or checksum tolerance. Even1ULP value tampering fails exact hash check.
- Existing sourceSHA attribution, category,budget,constraints,uniqueN,candidateorder andseed semantics preserved. No new drawing-provenance claim.
- RED reproduced before sourcefix;42focusedtests PASS;RufftwofilesPASS. Includes exact counterexample preserving originalSHA, normalize-once spy,1ULPtamper, rehashed invalidmodel/bank/source rejection and pre-existing timeout/feasibility tests.
- Independent AST comparison of searchbody frombudgetloop onward to before-source shows identical code. No objective/default/exchangebehavior changes or8draw reruns.

Source `/Users/turshevr/toto-ai/src/toto_ai/research/feasible_robust_exchange.py`
SHA256 `959f6f223da3514de80d9e915d15957fa1faa7a8ddd8730ca513e240261448f7`

Tests `/Users/turshevr/toto-ai/tests/test_feasible_robust_exchange.py`
SHA256 `60a30f55fd287df803d9459f7a8f03173e257acd69469f3fab22627725aebf3d`

Patch: /Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/P2-normalization-fix/fix.patch
Logs/REDconditions in siblingJSON and ownignoredreportdirectory. No Sports/DB/scheduler/memory/Git/publication edits. Next: independentreview by Huygens.
