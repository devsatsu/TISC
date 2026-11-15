# Sample verification

Executed on Current_Bills/CB1.jpeg with PaddleOCR 3.3.1, PaddlePaddle
3.2.0 CPU. Models downloaded successfully: PP-OCRv5_server_det and
en_PP-OCRv5_mobile_rec. OCR produced 141 text boxes.

Manual comparison against the supplied photograph:

| Field | Extracted | Photograph comparison |
|---|---|---|
| Bill date | 2026-07-04 | matches 04-07-2026 |
| Present KWH | 5343 | matches |
| Previous KWH | 4771 | matches |
| Energy charges | 4409.75 | matches |
| Fixed charges | 50.00 | matches |
| Customer charges | 55.00 | matches |
| Net payable | 4530.36 | matches |
| Due date | 2026-07-18 | matches 18-07-2026 |
| Multiplier | 1.0 | matches |
| Billed units | null, ambiguous | printed 572; candidates 243 and 572 |

The adjacent AVG UNITS value 243 overlaps the BILLED UNITS label's
bounding box enough to satisfy the configured row heuristic. The extractor
retains both candidates and does not silently choose one. No configured
fields were not_found; one is ambiguous. No mismatch was found among the
nine automatically extracted values.

Payment-summary completeness passes. Consumption-summary completeness
does not pass. Reading arithmetic is not applicable: units are unresolved
and simple-difference billing assumptions have not been confirmed.
Final amount reconciliation is intentionally not performed.

Replay into Replay_Results/CB1 reproduces the extraction. Nine focused
synthetic tests pass. Both existing quality-analysis commands still run.
These tests establish behavior for the tested cases, not general OCR accuracy
or support for other bill templates. Partial photos are processed independently.

First install required network approval; first inference required model-cache
access. Both completed successfully. No source images were modified.
