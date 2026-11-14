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
