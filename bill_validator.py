"""Validation never changes extracted values or certifies OCR correctness."""
from decimal import Decimal


def validate(fields, lookup):
    review = []
    for name, field in fields.items():
        valid = field["status"] == "extracted"
        field["validation_results"] = [{"check":"format","status":"passed" if valid else "not_applicable","reason":"Parsed format does not establish OCR correctness." if valid else "No unambiguous parsed value."}]
        if not valid:
            review.append({"field":name,"action":"Compare label and nearby value with source photograph.","reason":field["status"]})
    features = {}
    for feature in ("payment_summary","consumption_summary"):
        missing = [d["id"] for d in lookup["fields"] if feature in d["required_for"] and fields[d["id"]]["status"] != "extracted"]
        features[feature] = {"complete":not missing,"missing_fields":missing}
    ids = ("present_kwh","previous_kwh","meter_multiplier","units_consumed")
    arithmetic = {"status":"not_applicable","reason":"Requires all readings, explicit multiplier, and confirmed simple-difference billing assumptions."}
    if lookup.get("billing_assumptions",{}).get("simple_reading_difference_supported") and all(fields[k]["status"]=="extracted" for k in ids):
        present, previous, multiplier, units = (Decimal(fields[k]["value"]) for k in ids)
        if present >= previous and multiplier > 0:
            expected = (present-previous)*multiplier
            arithmetic = {"status":"passed" if expected==units else "failed","expected_units":str(expected),"reason":"(Present - previous) * explicit multiplier under configured billing assumptions."}
    return {"feature_completeness":features,"consumption_arithmetic":arithmetic,"amount_reconciliation":{"status":"not_applicable","reason":"Other charges, credits and adjustments are not fully modeled."},"review_items":review,"retake_required":None,"note":"Format validity is not OCR correctness. Missing fields may be outside this partial photo."}
