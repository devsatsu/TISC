"""One backend contract for CLI, API, saved OCR and multiple photos."""
import argparse
import json
from pathlib import Path
from uuid import uuid4
from decimal import Decimal
from field_extractor import extract
from bill_validator import validate
from ocr_reader import read_ocr, save_json

ROOT = Path(__file__).resolve().parent
LABELS = {
    "bill_date": ("బిల్లు తేదీ", "ఈ తేదీన బిల్లు జారీ అయింది."),
    "present_kwh": ("ప్రస్తుత మీటర్ రీడింగ్", "బిల్లులో నమోదైన ప్రస్తుత విద్యుత్ మీటర్ రీడింగ్."),
    "previous_kwh": ("గత మీటర్ రీడింగ్", "బిల్లులో నమోదైన గత విద్యుత్ మీటర్ రీడింగ్."),
    "units_consumed": ("వినియోగించిన యూనిట్లు", "ఈ బిల్లులో చూపించిన విద్యుత్ వినియోగం."),
    "energy_charges": ("విద్యుత్ వినియోగ ఛార్జీలు", "విద్యుత్ వినియోగానికి బిల్లులో చూపించిన మొత్తం."),
    "fixed_charges": ("స్థిర ఛార్జీలు", "బిల్లులో ప్రత్యేకంగా చూపించిన స్థిర ఛార్జీలు."),
    "customer_charges": ("కస్టమర్ ఛార్జీలు", "బిల్లులో చూపించిన కస్టమర్ సేవా ఛార్జీలు."),
    "net_payable": ("చెల్లించవలసిన మొత్తం", "ఇతర ఛార్జీలు, సర్దుబాట్లతో కలిపి బిల్లులో చూపించిన తుది మొత్తం."),
    "due_date": ("చెల్లింపు గడువు", "బిల్లులో పేర్కొన్న చెల్లింపు చివరి తేదీ."),
    "meter_multiplier": ("మీటర్ గుణకం", "మీటర్ రీడింగ్ ఆధారంగా వినియోగాన్ని లెక్కించడానికి ఉపయోగించే గుణకం."),
}


def merge(reports, lookup):
    merged = {}
    for definition in lookup["fields"]:
        key = definition["id"]
        evidence = [{"photo_id":r["photo_id"], **r["fields"][key]} for r in reports]
        extracted = [e for e in evidence if e["status"] == "extracted"]
        def canonical(value):
            return Decimal(value) if definition["type"] == "decimal" else value
        values = {canonical(e["value"]) for e in extracted}
        uncertain = any(e["status"] in ("ambiguous_match", "invalid_format", "label_found_value_unreadable") for e in evidence)
        conflict = len(values) > 1
        selected = extracted[0]["value"] if len(values) == 1 and not uncertain else None
        merged[key] = {"value":selected,"status":"conflict" if conflict else "extracted" if selected is not None else "needs_review" if extracted or uncertain else "not_found","evidence":evidence,"review_reason":"Compare conflicting or uncertain readings across photos." if conflict or uncertain else None}
    return merged


def explain(fields):
    sections = []
    for key, field in fields.items():
        label, description = LABELS.get(key, (key, "బిల్లులో చూపించిన వివరాలు."))
        value = field["value"]
        if value is None:
            text = "ఈ వివరాన్ని స్పష్టంగా గుర్తించలేకపోయాము. బిల్లు ఫోటోతో సరిపోల్చి చూడండి."
        else:
            shown = "-".join(reversed(value.split("-"))) if key in ("bill_date","due_date") else value
            if key.endswith("charges") or key == "net_payable":
                shown = "₹" + shown
            text = f"{label}: {shown}. {description}"
        sections.append({"field":key,"title":label,"text":text,"requires_review":value is None})
    return {"language":"te","title":"మీ విద్యుత్ బిల్లు వివరాలు","sections":sections,"notes":["ఇవి ఫోటోల నుంచి చదివిన వివరాలు. చెల్లించే ముందు అసలు బిల్లుతో సరిపోల్చండి.","ఇతర ఛార్జీలు, రాయితీలు, సర్దుబాట్లు ఉండవచ్చు. చూపించిన మూడు ఛార్జీలతో మాత్రమే మొత్తం లెక్కించలేదు."]}


def process(images=(), ocr_files=(), output_root=ROOT/"Backend_Results", lookup_path=ROOT/"lookups/ape_bill_v1.json", quality=False):
    if not 1 <= len(images)+len(ocr_files) <= 10:
        raise ValueError("Provide 1 to 10 photos or saved OCR files belonging to one bill.")
    lookup = json.loads(Path(lookup_path).read_text(encoding="utf-8"))
    job_id = uuid4().hex
    output = Path(output_root)/job_id
    output.mkdir(parents=True)
    reports, errors = [], []
    for index, (path, replay) in enumerate([(p,False) for p in images]+[(p,True) for p in ocr_files]):
        photo_id = f"photo_{index+1}"
        folder = output/photo_id
        folder.mkdir()
        try:
            ocr = json.loads(Path(path).read_text(encoding="utf-8")) if replay else read_ocr(path, folder)
            save_json(folder/"ocr_raw.json", ocr)
            fields, unmatched = extract(ocr, lookup)
            validation = validate(fields, lookup)
            report = {"photo_id":photo_id,"source_photo":ocr["source_photo"],"fields":fields,"validation":validation}
            reports.append(report)
            save_json(folder/"extracted_fields.json",report)
            save_json(folder/"unmatched_text.json",unmatched)
            if quality and not replay:
                try:
                    from analyze_image import analyze
                    analyze(Path(path),folder/"quality")
                except Exception as exc:
                    errors.append({"photo_id":photo_id,"stage":"quality","message":str(exc)})
        except Exception as exc:
            errors.append({"photo_id":photo_id,"stage":"ocr","message":str(exc)})
    fields = merge(reports,lookup)
    validation = validate(fields,lookup)
    result = {"schema_version":"2.0","job_id":job_id,"lookup_version":lookup["version"],"status":"failed" if not reports else "needs_review" if errors or any(f["status"]!="extracted" for f in fields.values()) else "completed","photos":[{"photo_id":r["photo_id"],"source_photo":r["source_photo"]} for r in reports],"fields":fields,"validation":validation,"explanation":explain(fields),"errors":errors,"coverage":{"same_bill":"user_supplied_grouping_not_verified","complete_bill":None},"retake_required":None}
    save_json(output/"result.json",result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("images",nargs="*",type=Path)
    parser.add_argument("--ocr-json",nargs="+",default=[],type=Path)
    parser.add_argument("--output-dir",type=Path,default=ROOT/"Backend_Results")
    parser.add_argument("--quality",action="store_true")
    args=parser.parse_args()
    result=process(args.images,args.ocr_json,args.output_dir,quality=args.quality)
    print(f"{result['status']}: {args.output_dir/result['job_id']/'result.json'}")
