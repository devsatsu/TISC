"""Measure image characteristics for bill photographs; results are uncalibrated."""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def metric(value, method, units=None, status="measured", reason=None):
    item = {"value": value, "method": method, "status": status}
    if units is not None:
        item["units"] = units
    if reason:
        item["reason"] = reason
    return item


def read_color(path):
    # OpenCV IMREAD_COLOR ignores EXIF orientation: stored pixel orientation is
    # preserved, no transform is applied, and EXIF orientation is not available.
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not decode image: {path}")
    return image


def region_bounds(height, overlap):
    # Three equal-height windows. Adjacent windows share overlap * window pixels.
    window = max(1, round(height / (3 - 2 * overlap)))
    stride = max(1, round(window * (1 - overlap)))
    starts = [0, stride, min(2 * stride, max(0, height - window))]
    return {n: (s, min(height, s + window)) for n, s in zip(("top", "middle", "bottom"), starts)}


def measurements(gray, dark, bright):
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    p5, p50, p95 = np.percentile(gray, [5, 50, 95])
    return {
        "sharpness": metric(float(lap.var()), "Variance of grayscale cv2.Laplacian(gray, CV_64F, ksize=3)", "intensity^2"),
        "contrast": {
            "grayscale_standard_deviation": metric(float(gray.std()), "Population standard deviation; intensity-spread proxy, not text-to-paper contrast", "intensity levels"),
            "p95_minus_p5": metric(float(p95-p5), "Grayscale P95 minus P5; intensity-spread proxy, not text-to-paper contrast", "intensity levels"),
        },
        "lighting": {
            "mean": metric(float(gray.mean()), "Mean grayscale brightness", "8-bit intensity (0-255)"),
            "median": metric(float(p50), "Median grayscale brightness", "8-bit intensity (0-255)"),
            "p5": metric(float(p5), "Fifth percentile grayscale brightness", "8-bit intensity (0-255)"),
            "p50": metric(float(p50), "Fiftieth percentile grayscale brightness", "8-bit intensity (0-255)"),
            "p95": metric(float(p95), "Ninety-fifth percentile grayscale brightness", "8-bit intensity (0-255)"),
            "fraction_at_or_below_dark_cutoff": metric(float(np.mean(gray <= dark)), f"Fraction of pixels <= configurable cutoff {dark}", "fraction"),
            "fraction_at_or_above_bright_cutoff": metric(float(np.mean(gray >= bright)), f"Fraction of pixels >= configurable cutoff {bright}", "fraction"),
        },
    }


def find_boundary(gray):
    """Conservative interior convex quadrilateral candidate from edges/contours."""
    h, w = gray.shape
    scale = min(1.0, 1200 / max(h, w))
    preview = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    edges = cv2.Canny(cv2.GaussianBlur(preview, (5, 5), 0), 40, 130)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ph, pw = preview.shape
    choices = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
        area = cv2.contourArea(contour) / float(ph * pw)
        if not 0.08 <= area <= 0.96:
            continue
        poly = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
        if len(poly) != 4 or not cv2.isContourConvex(poly):
            continue
        pts = poly.reshape(4, 2).astype(float) / scale
        center = pts.mean(axis=0)
        pts = pts[np.argsort(np.arctan2(pts[:, 1]-center[1], pts[:, 0]-center[0]))]
        pts = np.roll(pts, -int(np.argmin(pts.sum(axis=1))), axis=0)
        if np.any(pts[:,0] < 2) or np.any(pts[:,1] < 2) or np.any(pts[:,0] > w-3) or np.any(pts[:,1] > h-3):
            continue
        choices.append((area, pts))
    return (max(choices, key=lambda x: x[0]) if choices else None), edges


def save_image(path, pixels):
    ok, buffer = cv2.imencode(path.suffix, pixels)
    if not ok:
        raise OSError(f"Could not encode {path}")
    buffer.tofile(path)


def image_overview(details, capture_type="unknown"):
    """Plain-language observations; comparisons are within this image only."""
    gm = details["global_measurements"]
    regions = details["regional_measurements"]
    available = {name: data for name, data in regions.items() if data.get("coordinates_xyxy")}
    observations = {}
    for key, label, metric_key in (
        ("sharpness", "edge detail", None),
        ("contrast", "light-to-dark variation", "grayscale_standard_deviation"),
        ("lighting", "brightness", "median"),
    ):
        values = {name: (data[key] if metric_key is None else data[key][metric_key])["value"] for name, data in available.items()}
        if values and max(values.values()) != min(values.values()):
            low, high = min(values, key=values.get), max(values, key=values.get)
            observations[key] = f"The {low} has less {label} than the {high}."
        else:
            observations[key] = f"No regional difference in {label} was measured." if values else "Image too small to compare regions."
    observations["sharpness"] += " Text clarity is not yet confirmed."
    observations["contrast"] += " Text readability is not yet confirmed."
    observations["lighting"] += " This does not confirm shadows or glare."
    angle = gm["rotation_skew"]["skew_angle"]["value"]
    observations["rotation"] = "Tilt could not be estimated reliably." if angle is None else f"Detected lines tilt about {abs(angle):.1f} degrees {'clockwise' if angle >= 0 else 'counterclockwise'}. Text orientation is unconfirmed."
    found = details["geometry"]["perspective"]["quadrilateral_corners"]["value"] is not None
    observations["perspective"] = "A possible page outline was found; camera distortion is unconfirmed." if found else "Full page corners were not found; camera distortion could not be assessed."
    observations["framing"] = "Part of a bill, as specified by you. Missing text and combined bill coverage have not been checked." if capture_type == "partial_bill" else "Full bill coverage and cut-off text have not been confirmed."
    dims = details["image"]["decoded_dimensions"]
    observations["resolution"] = f"{dims['width']} x {dims['height']} pixels. Enough detail for reading small text has not been confirmed."
    return {
        "image_id": Path(details["image"]["filename"]).stem,
        "capture_type": capture_type,
        "overview": observations,
        "summary": "Image measured successfully. Reading quality and need for a retake are not yet determined.",
        "next_step": "Review the three photos together for overlapping text and missing bill sections." if capture_type == "partial_bill" else "Review the image for readable text and complete coverage.",
        "retake_required": None,
        "processing": {"status": "Measurements and preview images saved; no image corrections applied.", "processed_image_path": None, "actions_applied": []},
    }


def analyze(image_path, output_dir, overlap=.2, dark_cutoff=5, bright_cutoff=250, capture_type="unknown"):
    if not 0 <= overlap < .5:
        raise ValueError("overlap must be >= 0 and < 0.5")
    if not 0 <= dark_cutoff <= 255 or not 0 <= bright_cutoff <= 255:
        raise ValueError("brightness cutoffs must be in [0, 255]")
    image_path = Path(image_path)
    color = read_color(image_path)
    h, w = color.shape[:2]
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    whole = measurements(gray, dark_cutoff, bright_cutoff)
    bounds = region_bounds(h, overlap) if h >= 9 else {}
    regional = {}
    for name, (y0, y1) in bounds.items():
        regional[name] = {"coordinates_xyxy": [0, y0, w, y1], **measurements(gray[y0:y1], dark_cutoff, bright_cutoff)}
    if len(regional) == 3:
        medians = [regional[n]["lighting"]["median"]["value"] for n in ("top", "middle", "bottom")]
        whole["lighting"]["regional_median_variation"] = metric(float(np.std(medians)), "Population standard deviation of top/middle/bottom regional median brightness", "intensity levels")
    else:
        whole["lighting"]["regional_median_variation"] = metric(None, "Regional medians unavailable", "intensity levels", "unavailable", "Image too small for three non-empty regions.")
        regional = {n: {"coordinates_xyxy": None, "status": "unavailable", "reason": "Image too small for three non-empty horizontal regions."} for n in ("top", "middle", "bottom")}

    # Probabilistic Hough lines; exclude the outer 8% at top and bottom.
    inset = max(1, round(h * .08))
    roi = gray[inset:max(inset+1, h-inset)]
    line_edges = cv2.Canny(cv2.GaussianBlur(roi, (3,3), 0), 40, 120)
    lines = cv2.HoughLinesP(line_edges, 1, np.pi/180, max(20,w//20), minLineLength=max(20,w//12), maxLineGap=max(5,w//100))
    angles = []
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0,:]:
            angle = math.degrees(math.atan2(int(y2-y1), int(x2-x1)))
            while angle >= 90: angle -= 180
            while angle < -90: angle += 180
            if abs(angle) <= 7: angles.append(angle)
    enough = len(angles) >= 5
    skew = metric(float(np.median(angles)) if enough else None,
        "Median near-horizontal probabilistic Hough line angle; x right, y down, positive slopes down-right; outer 8% height excluded",
        "degrees", "estimated" if enough else "unavailable",
        None if enough else f"Found {len(angles)} qualifying line segments; at least 5 required.")

    candidate, boundary_edges = find_boundary(gray)
    null_metric = lambda method, units=None, reason="No reliable bill boundary candidate.": metric(None, method, units, "unavailable", reason)
    if candidate is None:
        perspective = {"quadrilateral_corners": null_metric("Conservative edge/contour quadrilateral candidate", "pixels"), "edge_lengths": null_metric("Euclidean distances between corners", "pixels"), "opposite_edge_ratios": null_metric("Opposite edge length ratios", "ratio")}
        framing = {"bounding_box_xyxy": null_metric("Candidate boundary bounds", "pixels"), "area_fraction": null_metric("Boundary area / image area", "fraction"), "touches_image_boundary": null_metric("Candidate corners compared with image bounds"), "text_clipping": null_metric("Not inferred from boundary contact", reason="Text clipping needs additional evidence."), "content_completeness": null_metric("Not assessed", reason="Partial receipt photographs can be valid; completeness is not assessed.")}
    else:
        area, pts = candidate
        lengths = [float(np.linalg.norm(pts[(i+1)%4]-pts[i])) for i in range(4)]
        xmin,ymin = pts.min(axis=0); xmax,ymax = pts.max(axis=0)
        perspective = {"quadrilateral_corners": metric(pts.tolist(), "Convex four-corner contour candidate, clockwise from smallest x+y point", "pixels", "estimated"), "edge_lengths": metric(lengths, "Euclidean distances between ordered corners", "pixels", "estimated"), "opposite_edge_ratios": metric([lengths[0]/lengths[2], lengths[1]/lengths[3]], "Top/bottom and right/left edge ratios", "ratio", "estimated")}
        framing = {"bounding_box_xyxy": metric([float(xmin),float(ymin),float(xmax),float(ymax)], "Axis-aligned candidate bounds", "pixels", "estimated"), "area_fraction": metric(float(area), "Candidate polygon area / image area", "fraction", "estimated"), "touches_image_boundary": metric(bool(xmin<=2 or ymin<=2 or xmax>=w-3 or ymax>=h-3), "Candidate corners within 2 pixels of image boundary", status="estimated"), "text_clipping": null_metric("Not inferred from boundary contact", reason="Boundary contact does not prove text is cut off."), "content_completeness": null_metric("Not assessed", reason="Partial receipt photographs can be valid; completeness is not assessed.")}

    rotation = {"skew_angle": skew, "evidence": {"qualifying_line_count": len(angles), "maximum_absolute_angle_degrees": 7, "line_overlay": "06_line_candidates_visualization.png" if lines is not None else None}, "upside_down_text_detection": null_metric("Line angles do not establish upright text", reason="No text-orientation classifier is implemented."), "deskew_applied": False}
    detailed_report = {
        "schema_version": "1.0",
        "image": {"path": str(image_path), "filename": image_path.name, "original_dimensions": {"width": w, "height": h}, "decoded_dimensions": {"width": w, "height": h}, "exif_orientation": metric(None, "OpenCV decoder does not expose EXIF orientation", status="unavailable", reason="No EXIF parser installed."), "orientation_applied_during_decoding": False, "coordinate_convention": "x right, y down; origin at top-left; decoded stored pixel coordinates"},
        "libraries": {"opencv": cv2.__version__, "numpy": np.__version__},
        "analysis_configuration": {"laplacian_kernel_size": 3, "regional_overlap_fraction_of_window": overlap, "regional_window_formula": "height/(3-2*overlap); stride=window*(1-overlap)", "dark_pixel_cutoff_inclusive": dark_cutoff, "bright_pixel_cutoff_inclusive": bright_cutoff, "measurements_use_native_resolution": True, "boundary_preview_max_dimension": 1200, "boundary_corners_mapped_to_native_coordinates": True},
        "global_measurements": {**whole, "rotation_skew": rotation, "resolution": {"width": metric(w,"Decoded width","pixels"), "height": metric(h,"Decoded height","pixels"), "megapixels": metric(w*h/1_000_000,"width*height/1,000,000","MP"), "aspect_ratio": metric(w/h,"width/height","ratio"), "estimated_character_height": metric(None,"No defensible character-height method implemented","pixels","unavailable","Would require character detection; OCR is not used.")}},
        "regional_measurements": regional,
        "geometry": {"perspective": perspective, "framing": framing},
        "warnings_and_limitations": ["Measurements are uncalibrated; no acceptance decision is made.", "Global and regional pixels may include background; horizontal regions are spatial bands, not semantic bill sections.", "Lighting fractions do not identify glare, underexposure, or lost information.", "No image enhancement, deskew, rotation, warp, or crop is applied.", "Boundary detection is a candidate heuristic and may not represent the bill.", "OpenCV IMREAD_COLOR preserves stored orientation and does not apply EXIF orientation."],
        "calibration_status": "uncalibrated", "acceptance_decision": None,
    }
    stage = Path(output_dir) / image_path.stem
    stage.mkdir(parents=True, exist_ok=True)
    save_image(stage/"01_analysis_input.png", color)
    save_image(stage/"02_grayscale.png", gray)
    # convertScaleAbs takes absolute values and saturates to 8-bit; it does not normalize.
    save_image(stage/"03_laplacian_response_visualization.png", cv2.convertScaleAbs(cv2.Laplacian(gray,cv2.CV_64F,ksize=3)))
    region_overlay = color.copy()
    for name,(y0,y1) in bounds.items():
        cv2.line(region_overlay,(0,y0),(w-1,y0),(255,0,0),2)
        cv2.putText(region_overlay,name,(8,min(h-1,y0+24)),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,0,0),2)
    save_image(stage/"04_regions_visualization.png",region_overlay)
    files=["01_analysis_input.png","02_grayscale.png","03_laplacian_response_visualization.png","04_regions_visualization.png"]
    if candidate is not None:
        _, pts = candidate
        cv2.polylines(region_overlay,[np.rint(pts).astype(np.int32)],True,(0,255,0),3)
        save_image(stage/"05_boundary_candidate_visualization.png",region_overlay)
        files.append("05_boundary_candidate_visualization.png")
    if lines is not None:
        overlay=color.copy()
        for x1,y1,x2,y2 in lines[:,0,:]:
            cv2.line(overlay,(int(x1),int(y1+inset)),(int(x2),int(y2+inset)),(0,0,255),2)
        save_image(stage/"06_line_candidates_visualization.png",overlay)
        files.append("06_line_candidates_visualization.png")
    detailed_report["debug_outputs"]={"directory":str(stage),"visualizations_only":True,"files":files}
    compact_report = image_overview(detailed_report, capture_type)
    (stage/"report.json").write_text(json.dumps(compact_report,indent=2,allow_nan=False),encoding="utf-8")
    (stage/"detailed_measurements.json").write_text(json.dumps(detailed_report,indent=2,allow_nan=False),encoding="utf-8")
    return compact_report, stage/"report.json"


def main():
    root=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image",nargs="?",type=Path,default=root/"Current_Bills"/"CB1.jpeg")
    parser.add_argument("--output-dir",type=Path,default=root/"Quality_Stages")
    parser.add_argument("--overlap",type=float,default=.2)
    parser.add_argument("--dark-cutoff",type=int,default=5)
    parser.add_argument("--bright-cutoff",type=int,default=250)
    parser.add_argument("--capture-type", choices=("unknown", "partial_bill", "full_bill"), default="unknown")
    args=parser.parse_args()
    try:
        report,path=analyze(args.image,args.output_dir,args.overlap,args.dark_cutoff,args.bright_cutoff,args.capture_type)
    except (OSError,ValueError,cv2.error) as exc:
        parser.exit(1,f"Error: {exc}\n")
    print(f"Report: {path}")
    print(report["summary"])


if __name__=="__main__":
    main()
