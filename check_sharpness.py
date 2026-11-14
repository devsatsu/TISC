"""Check image sharpness using the variance of the grayscale Laplacian."""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def check_sharpness(
    image_path: Path, threshold: float = 100, stages_root: Path | None = None
) -> dict:
    """Higher scores indicate more high-frequency detail; calibrate per image type."""
    if not math.isfinite(threshold) or threshold < 0:
        raise ValueError("Threshold must be a finite, non-negative number.")
    # imdecode supports Windows paths containing non-ASCII characters.
    color = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if color is None:
        raise ValueError(f"Could not decode image: {image_path}")
    image = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(image, cv2.CV_64F)
    score = float(laplacian.var())

    if stages_root is not None:
        stage_dir = stages_root / image_path.stem
        stage_dir.mkdir(parents=True, exist_ok=True)

        def save_stage(name: str, pixels: np.ndarray) -> None:
            output = stage_dir / f"{name}.png"
            if not cv2.imwrite(str(output), pixels):
                raise OSError(f"Could not save stage image: {output}")

        save_stage("01_input", color)
        save_stage("02_grayscale", image)
        # Normalize absolute Laplacian values to make edge responses visible.
        laplacian_visual = cv2.convertScaleAbs(laplacian)
        save_stage("03_laplacian_edges", laplacian_visual)
        overlay = color.copy()
        overlay[laplacian_visual > 0] = (0, 0, 255)
        save_stage("04_edges_on_input", overlay)
        report = {
            "sharpness_score": round(score, 2),
            "threshold": threshold,
            "possibly_blurry": score < threshold,
        }
        label = f"Laplacian variance: {score:.2f} | threshold: {threshold:g} | possibly blurry: {score < threshold}"
        summary = np.full((100, 900, 3), 255, dtype=np.uint8)
        cv2.putText(summary, label[:90], (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 2)
        save_stage("05_sharpness_result", summary)
        (stage_dir / "result.json").write_text(json.dumps(report, indent=4), encoding="utf-8")

    return {
        "sharpness_score": round(score, 2),
        "threshold": threshold,
        "possibly_blurry": score < threshold,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "image", nargs="?", type=Path,
        default=Path(__file__).resolve().parent / "Current_Bills" / "CB1.jpeg",
        help="Image path (default: Current_Bills/CB1.jpeg beside this script).",
    )
    parser.add_argument("--threshold", type=float, default=100)
    parser.add_argument(
        "--stages-dir", type=Path,
        default=Path(__file__).resolve().parent / "Sharpness_Stages",
        help="Folder for saved processing-stage images (default: Sharpness_Stages).",
    )
    args = parser.parse_args()
    try:
        result = check_sharpness(args.image, args.threshold, args.stages_dir)
    except (OSError, ValueError, cv2.error) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(result, indent=4))


if __name__ == "__main__":
    main()
