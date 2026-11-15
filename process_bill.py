"""Independent per-photo OCR, lookup extraction and validation."""
import argparse
import json
import shutil
from pathlib import Path
from ocr_reader import read_ocr, save_json
from field_extractor import extract
from bill_validator import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image",nargs="?",type=Path)
    parser.add_argument("--lookup",type=Path,default=Path(__file__).parent/"lookups/ape_bill_v1.json")
    parser.add_argument("--output-dir",type=Path,default=Path(__file__).parent/"Bill_Results")
    parser.add_argument("--ocr-json",type=Path,help="Replay the saved stable OCR schema without PaddleOCR.")
    parser.add_argument("--quality",action="store_true")
    args = parser.parse_args()
    if not args.image and not args.ocr_json:
        parser.error("Provide an image or --ocr-json")
    try:
        lookup = json.loads(args.lookup.read_text(encoding="utf-8"))
        if args.ocr_json:
            ocr = json.loads(args.ocr_json.read_text(encoding="utf-8"))
            output = args.output_dir/Path(ocr["source_photo"]).stem
            output.mkdir(parents=True,exist_ok=True)
            save_json(output/"ocr_raw.json",ocr)
            for name in ("analysis_input.png", "ocr_boxes.png"):
                source = args.ocr_json.parent/name
                target = output/name
                if source.exists() and source.resolve() != target.resolve():
                    shutil.copy2(source, target)
        else:
            output = args.output_dir/args.image.stem
            ocr = read_ocr(args.image,output)
        fields, unmatched = extract(ocr,lookup)
        validation = validate(fields,lookup)
        metadata = {"schema_version":"1.0","lookup_version":lookup["version"],"source_photo":ocr["source_photo"],"image":ocr["image"],"ocr_settings":ocr["ocr_settings"],"package_versions":ocr.get("package_versions",{})}
        save_json(output/"extracted_fields.json",{**metadata,"fields":fields})
        save_json(output/"validation_report.json",{**metadata,**validation})
        save_json(output/"unmatched_text.json",{**metadata,"boxes":unmatched})
        if args.quality:
            try:
                from analyze_image import analyze
                analyze(Path(ocr["source_photo"]),output/"quality")
            except Exception as exc:
                print(f"Optional quality diagnostics failed; OCR results retained: {exc}")
        print(f"Results: {output}")
        for name, field in fields.items():
            print(f"{name}: {field['status']} = {field['value']}")
    except (OSError,ValueError,ImportError,KeyError) as exc:
        parser.exit(1,f"Pipeline error: {exc}\n")


if __name__ == "__main__":
    main()
