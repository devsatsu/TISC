# Bill photo measurements

This project reports uncalibrated image measurements for electricity-bill photographs. The analyzer does not OCR, enhance, crop, rotate, deskew, warp, or reject images. It makes no acceptance decision.

## Install and run

```powershell
py -m pip install -r requirements.txt
py analyze_image.py
py analyze_image.py "Current_Bills/CB1.jpeg"
py analyze_image.py "path/to/image.jpeg" --output-dir "Quality_Stages"
```

Optional controls are `--overlap` (default 0.2, fraction of each regional window shared by an adjacent window), `--dark-cutoff` (default 5), and `--bright-cutoff` (default 250). Output is saved to `Quality_Stages/<image_stem>/report.json`, alongside diagnostic visualizations.

## Measurements

The JSON reports global and top, middle, and bottom horizontal-region measurements for Laplacian variance sharpness, grayscale standard deviation, P95-P5 spread, and brightness statistics. These contrast values are intensity-spread proxies, not direct text-to-paper contrast. Dark and bright pixel fractions use configurable inclusive cutoffs. Regional medians are summarized by their standard deviation.

Rotation/skew uses the median angle of near-horizontal probabilistic Hough line segments after excluding the outer 8% of image height. It reports unavailable when fewer than five qualifying segments are found. This does not identify upside-down text.

Perspective and framing use a conservative edge/contour quadrilateral candidate. Any geometry is descriptive and heuristic; unavailable geometry is represented by JSON null with a reason. Boundary contact does not establish text clipping. Resolution reports decoded dimensions, megapixels, and aspect ratio; character height remains unavailable.

All measurements use native decoded pixels. The three horizontal regions are spatial bands and can include background; they are not inferred bill sections. Candidate boundary detection may use a preview no larger than 1200 pixels on its longest side, with coordinates mapped back to native pixels.

## Decoding and EXIF

Images are read using OpenCV `imdecode` with bytes loaded by `numpy.fromfile`, supporting Unicode Windows paths. OpenCV's `IMREAD_COLOR` decoding policy is used: EXIF orientation is not applied, and the EXIF orientation tag is not read. The report records this explicitly, so stored pixel dimensions and coordinates are used consistently. No Pillow dependency is needed.

Visualization files are diagnostic displays only; no measurement is calculated from an overlay or display-normalized image. The Laplacian display uses absolute 8-bit saturated conversion and is not normalized to the full range. Green contours and red line segments are candidate responses, not proof of bill edges or text.

## Legacy sharpness command

`check_sharpness.py` remains available with its original threshold behavior:

```powershell
py check_sharpness.py
py check_sharpness.py "Current_Bills/CB1.jpeg" --threshold 100
```

The new report retains full precision for measurements and has no sharpness acceptance threshold. Its Laplacian kernel is explicitly 3; the legacy script uses OpenCV's default kernel size. Results can therefore differ slightly, and no previous score is hardcoded.

## Simple image overview

`report.json` now contains plain-language observations for all seven characteristics, a summary, a next step, and processing status. Technical measurements remain in `detailed_measurements.json`. Regional comparisons describe relative differences within one image; they are not calibrated quality ratings.

For a partial bill photo, run `python analyze_image.py "path/to/photo.jpeg" --capture-type partial_bill`. This capture type is supplied by the user, not detected. Each photo is analyzed separately; combined coverage, stitching, OCR, and image corrections are not performed.

## OCR and lookup extraction (separate optional pipeline)

Use Python 3.11 on Windows with a separate CPU environment:

```powershell
python -m venv .venv-ocr
.\.venv-ocr\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv-ocr\Scripts\python.exe process_bill.py "Current_Bills/CB1.jpeg" --lookup "lookups/ape_bill_v1.json"
python process_bill.py --ocr-json "Bill_Results/CB1/ocr_raw.json" --output-dir "Replay_Results"
```

PaddleOCR 3.3.1 uses its `predict` API with PaddlePaddle 3.2.0 CPU, PP-OCRv5 and English recognition. First execution downloads pretrained models and requires internet access and writable model caches. See the official API/install reference: https://www.paddleocr.ai/v3.3.1/en/quick_start.html . The stable OCR JSON retains the native engine result, settings, package versions, source path, text polygons and confidence when supplied. Replay needs only the base project dependencies. `--quality` adds optional diagnostics without blocking extraction. `--output-dir` changes the result root.

The OCR adapter explicitly ignores EXIF orientation and disables document rotation, unwarping and textline orientation. Coordinates refer to `analysis_input.png`, decoded at original resolution; source photos are unchanged. This policy is explicit in the adapter; older quality scripts use their existing OpenCV decode behavior.

`lookups/ape_bill_v1.json` is restricted to the supplied Andhra Pradesh format. Values are not stored in the lookup. Exact approved labels, adjacent split labels and row geometry are used. Geometric heuristics are configurable: at least 50% vertical overlap, at most 10 local text heights to the right, and 1.5 heights between split label fragments. Meter rows take the first reading position before dates/status. Competing values and shared numeric boxes require review. No fuzzy digit corrections are applied. Currency is serialized as Decimal strings; dates require DD-MM-YYYY.

Each result folder contains `ocr_raw.json`, `extracted_fields.json`, `validation_report.json`, `unmatched_text.json`, `analysis_input.png`, and `ocr_boxes.png`. Unknown labels and unresolved text remain in unmatched output. Replay writes JSON outputs; the source run retains its images. Missing fields are not proof of poor quality. Arithmetic requires an explicit multiplier and a confirmed simple-difference billing assumption in the lookup; it is disabled by default. The partial set of charges cannot reconcile the final amount. No automatic retake, merging, enhancement, translation, or UI is implemented.

Run focused extraction checks with `python -m unittest test_extraction -q`.

## Connected Python backend

Run one photo or multiple photos of the same bill:

```powershell
.\.venv-ocr\Scripts\python.exe bill_backend.py "Current_Bills/CB1.jpeg"
.\.venv-ocr\Scripts\python.exe bill_backend.py "photo1.jpeg" "photo2.jpeg" "photo3.jpeg"
python bill_backend.py --ocr-json "Bill_Results/CB1/ocr_raw.json"
.\.venv-ocr\Scripts\python.exe backend_server.py
```

Each run writes `Backend_Results/<job_id>/result.json`: merged values with per-photo evidence, validation, Telugu explanation, missing/conflicting fields, processing errors and coverage limitations. Photos are grouped by the caller; same-bill identity and full page coverage are not automatically verified. Disagreements remain unresolved. Equal numeric values such as 1 and 1.0 agree. Ambiguous evidence requires review even when another photo has a value. Telugu explanations use deterministic templates and do not invent tariffs or reconcile unmodeled charges. Optional `--quality` diagnostics do not block OCR.

The local API listens on http://127.0.0.1:8000. POST `/bills` with JSON `{"photos":[{"base64":"<image bytes encoded as base64>"}]}`. It returns HTTP 202 with a request_id and result_url. Poll GET `/bills/<request_id>` until a final result arrives. GET `/health` checks service availability. Limits: 10 photos, 10 MB each, 40 MB JSON body, 30 megapixels per decoded image. A single worker serializes CPU OCR jobs. Results persist under API_Results; interrupted jobs must be resubmitted after restart. Upload names are generated by the server. No additional server dependencies are required.

This is a local development API, not an internet deployment. Authentication, HTTPS, job retention/deletion, rate limits, a durable queue, and a production server are still deployment work before exposing it to phone users. The standard-library server is deliberately bound to loopback. No automatic image enhancement or image stitching occurs. Stored pixel orientation is used; callers should provide upright photos. Explanation coverage is limited to fields in the lookup; additional charges remain in unmatched OCR output.

Row association now also requires vertical centers within 0.4 local text heights. Override `maximum_center_offset_heights` in lookup geometry if calibrated against more photographs. This resolves the sample AVG UNITS/BILLED UNITS ambiguity without using arithmetic or fixed coordinates.
