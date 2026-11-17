"""Lookup-driven extraction; no digit corrections or sample values."""
import re
from datetime import datetime
from decimal import Decimal


def normalize(text):
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def parse_value(text, kind):
    text = text.strip()
    if kind == "date":
        if not re.fullmatch(r"\d{2}-\d{2}-\d{4}", text):
            raise ValueError("Expected DD-MM-YYYY")
        return datetime.strptime(text, "%d-%m-%Y").date().isoformat()
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise ValueError("Expected signed decimal")
    return str(Decimal(text.replace(",", "")))


def same_row(a, b, settings):
    ax, ay, ar, ab = a["bbox"]
    bx, by, br, bb = b["bbox"]
    height = max(1, min(ab-ay, bb-by))
    if abs((ay+ab-by-bb)/2)/height > settings.get("maximum_center_offset_heights", .4):
        return False
    return (min(ab, bb)-max(ay, by))/height >= settings["minimum_vertical_overlap"] and -height*.2 <= bx-ar <= settings["maximum_gap_heights"]*height


def extract(ocr, lookup):
    boxes = ocr["boxes"]
    settings = lookup["geometry"]
    fields = {}
    used = set()
    for definition in lookup["fields"]:
        candidates = []
        labels_found = []
        for box in boxes:
            groups = [[box]]
            # Adjacent OCR fragments can form a configured label.
            for other in boxes:
                if other["id"] != box["id"] and same_row(box, other, {**settings, "maximum_gap_heights": settings["split_label_gap_heights"]}):
                    groups.append([box, other])
            for group in groups:
                raw_label = " ".join(b["text"] for b in group)
                for alias in definition["labels"]:
                    if len(group) > 1 and normalize(raw_label) != normalize(alias):
                        continue
                    words = alias.split()
                    pattern = r"^\s*" + r"[\s.:]+".join(map(re.escape, words)) + r"(?=$|[\s:;=])\s*[:;=]?\s*"
                    match = re.match(pattern, raw_label, re.I)
                    if normalize(raw_label) == normalize(alias):
                        remainder = ""
                    elif match:
                        remainder = raw_label[match.end():]
                    else:
                        continue
                    labels_found.extend(b["id"] for b in group)
                    choices = [(remainder, group[-1])] if remainder else [(b["text"], b) for b in boxes if b["id"] not in [g["id"] for g in group] and same_row(group[-1], b, settings)]
                    if definition["extraction"].get("meter_row") and not remainder and choices:
                        # Reading must occupy the first box to the right, before date/status.
                        nearest = min(b["bbox"][0] for _, b in choices)
                        choices = [(t,b) for t,b in choices if b["bbox"][0] == nearest]
                    for raw, value_box in choices:
                        token = raw.strip()
                        if definition["extraction"].get("meter_row"):
                            token = token.split()[0] if token else ""
                        try:
                            value = parse_value(token, definition["type"])
                            error = None
                        except ValueError as exc:
                            value, error = None, str(exc)
                        candidates.append({"value":value,"raw_label":raw_label if not remainder else raw_label[:match.end()].strip(),"raw_value":raw,"label_box_ids":[b["id"] for b in group],"value_box_id":value_box["id"],"label_coordinates":[b["bbox"] for b in group],"value_coordinates":value_box["bbox"],"ocr_confidence":value_box.get("confidence"),"error":error})
        # Deduplicate equivalent evidence, while retaining competing values.
        unique = { (tuple(c["label_box_ids"]), c["value_box_id"], c["raw_value"]):c for c in candidates}
        candidates = list(unique.values())
        valid = [c for c in candidates if c["value"] is not None]
        chosen = valid[0] if len(valid) == 1 else None
        status = "extracted" if chosen else "ambiguous_match" if len(valid)>1 else "invalid_format" if candidates else "label_found_value_unreadable" if labels_found else "not_found"
        entry = {"value":chosen["value"] if chosen else None,"status":status,"matching_method":"exact_alias_and_row_geometry","source_photo":ocr["source_photo"],"raw_label":chosen["raw_label"] if chosen else None,"raw_value":chosen["raw_value"] if chosen else None,"ocr_box_ids":list(dict.fromkeys(labels_found + ([chosen["value_box_id"]] if chosen else []))),"label_coordinates":chosen["label_coordinates"] if chosen else None,"value_coordinates":chosen["value_coordinates"] if chosen else None,"ocr_confidence":chosen["ocr_confidence"] if chosen else None,"validation_results":[],"review_reason":None if chosen else "Review the source photo and retained candidates; this is not evidence of poor image quality.","candidates":candidates}
        fields[definition["id"]] = entry
        if not chosen and labels_found:
            entry["raw_label"] = " | ".join(b["text"] for b in boxes if b["id"] in labels_found)
            entry["label_coordinates"] = [b["bbox"] for b in boxes if b["id"] in labels_found]
            if len(candidates) == 1:
                entry["raw_value"] = candidates[0]["raw_value"]
                entry["value_coordinates"] = candidates[0]["value_coordinates"]
    # Shared numeric evidence cannot silently satisfy unrelated fields.
    assignments = {}
    for name, field in fields.items():
        if field["status"] == "extracted":
            candidate = next(c for c in field["candidates"] if c["value"] is not None)
            assignments.setdefault(candidate["value_box_id"], []).append(name)
    for names in assignments.values():
        if len(names)>1:
            for name in names:
                fields[name].update(value=None,status="ambiguous_match",review_reason="Numeric OCR box is shared with another field.")
    for field in fields.values():
        if field["status"] == "extracted":
            used.update(field["ocr_box_ids"])
    return fields, [b for b in boxes if b["id"] not in used]
