# Parallel G1 evaluation profile

The optional parallel G1 profile defaults to 65,536 raw remove/add pair evaluations
(a generic 2^16 work-count budget), replacing 50,000. Explicit typed overrides
remain supported; no drawing, bank or candidate-count special case is introduced.

An evaluation is counted before exposure rejection in the exact engine. For a
valid unique universe containing the initial N-coupon package, a complete round
has N × (U − N) evaluations. M probability models do not multiply this counter;
they multiply exact projection work on each exposure-admissible pair. Therefore
admission must not divide the raw-pair estimate by M or count only improvements.

N=166/U=489/M=4 has 53,618 raw pairs and is admitted by the new default without
removing or reordering candidates. For N=166, U=560 fits (65,404 pairs), while
U=561 does not (65,570 pairs). Above-cap inputs still skip the worker entirely.
The new default supplies 31.072% more count budget, not additional runtime.

No optimization objective, EPSILON, exposure/safety test, exact per-model
P13/P14/P15 non-degradation, consent or family-lineage rule changes. The profile
still permits one accepted swap, 50s cooperative engine budget, 60s hard worker
timeout and 30s publication reserve. Incomplete/time-exhausted evaluation keeps
the exact original fallback; this profile does not license partial-round output.
The serialized limits remain bound by existing request/config hashes.

Admission means permission to attempt the complete round, not evidence it will
finish within 50s or improve any package. This change has only unit/contract
evidence; no dense replay, fresh provider input, outcome or profitability claim.

## Subsequent accepted main evidence — 2026-09-06

The preceding author evidence boundary was pre-replay. After exact adoption, a
separate SAME frozen4998 NONFINAL research diagnostic completed53,618pairs, one
verified swap,40.928s engine time and all12 non-degradation checks. The overall
selector still chose quality-v3, not the refined robust family. This is modeled
research evidence, not final PLAY or predictive/profit validation. Publication
verification:24pytest PASS; Ruff3Pythonfiles PASS. No dense replay was repeated by
the publisher. See plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/G1_PROFILE_MAIN_ADOPTION_AND_REPLAY_HANDOFF.md.
