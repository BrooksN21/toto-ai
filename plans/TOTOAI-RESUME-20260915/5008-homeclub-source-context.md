# 5008 event9 — bounded home-club source context

Task TOTOAI-RESUME-20260915. Completed2026-09-15T21:21:03.133164+03:00; **3publicrequests**, no rerunofknownconflictingsources. Result: NEW_OFFICIAL_DOCUMENT_FOUND_KICKOFF_UNRESOLVED.

## New actual evidence
1. OfficialhomeclubWordPressAPI returned post11378, “Download or View – Willand Rovers F.C v Westbury Utd – Matchday Programme”: https://www.willandrovers.co.uk/download-or-view-willand-rovers-f-c-v-westbury-utd-matchday-programme/
2. Published/modified14September2026 at18:56:54UTC = **21:56:54MSK**; localAPI19:56:54. Bodycontainsprogramme link only, no kickoff/timezone. Publicationoffset is not kickoff proof.
3. PublicanonymousDriveviewer confirms filename **Matchday Programme2627Westbury.pdf**: https://drive.google.com/file/d/1jcL1R2DfP5RMNISP25glqYv27C5q3UQ-/view?usp=drive_link
4. Thirdrequestto viewer-provideddownloadURL returnedHTTP303 to https://drive.usercontent.google.com/download?id=1jcL1R2DfP5RMNISP25glqYv27C5q3UQ-&export=download . Stoppedat3requests rather than issuingadditionalredirectGET. No authorization/loginfailure, no proxy or contact.

## What remains
PDFbytesnotyetobtained; exactmatchdate/venue/kickoff/TZinsideprogramme **NOT VERIFIED**. Thus no proofresolvingknown19:30/19:45/leagueZconflict. No timeaccepted, no DB/catalog/jobs/code/memory/consent changes.

## Proposed next narrow action, not executed
OnepublicGETofthe exactcanonicaldownloadURLabove, bounded20s, inspectrelevantprogrammepagesforfixturedate/venue/kickoffandexplicitTZorclearcalendarcontract. Onlyifthatgenuinelyresolvesknownconflict shouldparentassignseparateexistingnative reviewed-evidenceimplementation. Do not usepublicationtimezoneasmatchtimezone or silentlyroundSofaseconds.

## Provenance
APIresponsebodySHA256: `4a6c933843246adc6f8db74bbda1eba57c471947de69179e427f398fe44ae1f3`. Exactpublicsourcepayload+publicationmetadata in `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/5008-homeclub-source-context-request1.json`; viewermetadata/hash inrequest2; redirectreceipt inrequest3. Viewer'sanonymousinternalconfiguration/tokenstrings werenotpersisted. Machinehandoff: `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/5008-homeclub-source-context.json`.
