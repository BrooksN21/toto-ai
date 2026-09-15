# 4996 retrospective recovery — 2026-09-05

Task:TOTOAI-4996-4997-RECOVERY-20260904; worker01a07108-e153-7df2-8597-397cb71b3589.
Scope:4996 retrospective only. No4997 changes, no primary settlement rerun,
no new sports API calls, no secrets, no remote/publication, no descendant.

## Root cause and repair
The runner supplied the archived upload-file byte SHA-256 to a comparison with
`PostDrawState.package_sha256`, which is the SHA-256 of comma-joined ordered
coupon strings. The source CSV byte SHA-256 is a third namespace.

Exact independently recomputed identities:
- source CSV bytes:906ca0c3e71e584771f41f7f7e239f7cb6d6873a3ee2411c695a6a6b047bdbf8
- upload bytes:42e6e55a1c6b7d642ad749257849e94e4216e57c6cacfa08d26fca74e9c44b37
- canonical coupons:f227a5374aba05c758a8d15cf4d4c06b8989f52cf54eced672c371a4d592b27d
All166 ordered coupons/stakes match. There was no package corruption.

New reusable `src/toto_ai/operations/retrospective_integrity.py` validates:
1.producer-loaded/self-hashed primary plan and expected immutable plan hash;
2.drawing identity, exact state path, source bytes, cost/stake/count;
3.producer-parsed canonical package hash, state schema/self-hash/identity;
4.complete-state semantic hash against semantic binding, never upload bytes.
Missing/pending state remains non-completion. Integrity guards were strengthened,
not bypassed. Original data/receipts/plans unchanged; retrospective executable
binding changed as an explicit recovery revision, with exact original runner,
execution plan and failed status archived under `noon-recovery-originals/`.
New revision plan hash:ee842c15e1fbb520cc70549b347927b65653d7b9ba33ad2d0de088a9b626c296.

## Verification
-15 new source-tree tests use genuine producer-generated postdraw plans/states,
 independent of ignored reports. Covers distinct hash namespaces, pending/missing,
 corrupt/re-signed foreign/schema/source/state/path/hash/cost cases.
-2 operational smoke tests validate replay self-hash encoding and REAL4996
 frozen binding through the actual caller, plus wrong-plan rejection.
-9 existing postdraw lifecycle tests passed; initial26 passed in2.05s; final30 with payoutfixture passed2.62s.
-Focused Ruff clean. No full2348-test suite: scoped fix, no commit in this task.
-Old synthetic regression merely compared two arbitrary hashes and never
 exercised the producer/consumer mapping; that explains why it missed this bug.

## Recovery and ownership
One existing entrypoint invocation, after exact LaunchAgent/PID duplicate check:
13:14:23MSK PID32988/tool session27789; child replay max1800seconds.
Next scheduled retrospective retry15:05MSK; existing report is checked/reused.
Replay is POST_DRAW_REPLAY_NOT_PRE_CUTOFF_SIDECAR, never an issued past forecast.
Terminal:RETROSPECTIVE_COMPLETE;exit0;replay188.51s.
Status file completion mtime:2026-09-05T13:17:33.183892+03:00. No owned processes remain.

## Final results and evidence
Current complete comparison (supersedes earlier provisional monetary estimates):
/Users/turshevr/toto-ai/reports/research/4996-equal-input-replay/screenshot-payout-comparison.md
Machine data:samepath.json;stateRETROSPECTIVE_COMPLETE;reporthash
c3563f0b5a32a876613297861c95cd48cb605515eb900c8efba55d56f4b9f283.

|Model|Best|Exact9/10/11/12/13/14/15|Return|Net|Evidence|
|---|---:|---|---:|---:|---|
|quality-v2|11(#54)|7/4/1/0/0/0/0|4058.16|-921.84|actualownerreceipt|
|sports-v2|11(#53)|9/3/1/0/0/0/0|3965.65|-1014.35|postdrawestimate|
|quality-v3|13(#84)|15/10/1/0/1/0/0|20183.91|15203.91|postdrawestimate|
|robust|13(#78)|10/12/2/0/1/0/0|21179.90|16199.90|postdrawestimate|

Primarysource rule4.2.1 verified directly2026-09-05:
https://cdndocs.baltbet.ru/uni/docs/sd_GameRules.pdf?v5= (PDFpages8–9).
Controlactualreceipt4058.16;fullprecisioncoefficientaggregate4058.15820.
First2886.71 estimate omitted categories;second4058.14 rounded too early.
Correctiontrail retained;rawcoefficient/receipt evidence separate, noDB/immutable
settlement rewrites. ReceiptID/image private local only, ignored byGit.
30focusedtests passed2.62s including4new payouttests;focusedRuffclean.

Reproducibility proof:noon-replay-provenance-proof.json.
ActualresultX222XX2111112X2;frozeninputresults empty;allgeneratorcalls precede
actualresult read at hybrid_replay.py294. Control reproducedexactly.
No complete historicalruntimehash attestation;no yesterday terminalparallel
packagesoractivationdecision. Replaycode/config/seedpath not proven equivalent
to yesterdayparallel. Therefore13today does NOT prove yesterdayeligible13release.
HighestP13control recomputed fromboundBK:position39,112212X122112XX,
P13=.00024092593202592184,actual7hits. Realizedbestposition54=11hits.

Source changes:src/toto_ai/operations/retrospective_integrity.py,
retrospective_payouts.py;tests/test_retrospective_integrity.py,
test_retrospective_payouts.py;existing generatedretrospective runner/plan;
operational smoke fixture,ACTIVE_PLAN,THREAD_COORDINATION,scopedreports.
Allfrozenbindings/receipts unchanged;originalrunner/plan/status archived.
No4997changes,nosettlementrerun,nopublication,noactiveownedprocess.
Nextparentcheckpoint14:30MSK4997;cutoff16:20MSK.
Parent13:18reports review/modelssetuprejected;registryreflectsblocker,
notactivechildren. Norespawn/workaround attempted.
