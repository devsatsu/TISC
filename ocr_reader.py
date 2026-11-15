"""PaddleOCR 3.x CPU adapter; explicit stored-pixel orientation policy."""
import json
import math
from importlib.metadata import version
from pathlib import Path
import cv2
import numpy as np


def save_json(path, data):
    def clean(value):
        if isinstance(value, np.ndarray):
            return clean(value.tolist())
        if isinstance(value, np.generic):
            return clean(value.item())
        if isinstance(value, dict):
            return {str(k):clean(v) for k,v in value.items()}
        if isinstance(value, (tuple,list)):
            return [clean(v) for v in value]
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    Path(path).write_text(json.dumps(clean(data), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def read_ocr(image_path, output):
    from paddleocr import PaddleOCR
    image_path = Path(image_path).resolve()
    image = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None:
        raise ValueError(f"Cannot decode {image_path}")
    settings = dict(device="cpu", lang="en", ocr_version="PP-OCRv5", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    engine = PaddleOCR(**settings)
    results = list(engine.predict(image))
    if len(results) != 1:
        raise ValueError("Expected exactly one image result")
    native = results[0].json
    if isinstance(native, str):
        native = json.loads(native)
    res = native.get("res", native)
    boxes = []
    for i, (text, poly) in enumerate(zip(res["rec_texts"], res["rec_polys"])):
        points = np.asarray(poly, dtype=float)
        score = res.get("rec_scores", [None]*len(res["rec_texts"]))[i]
        score = float(score) if score is not None else None
        boxes.append({"id":f"box_{i:04d}","text":text,"polygon":points.tolist(),"bbox":[float(points[:,0].min()),float(points[:,1].min()),float(points[:,0].max()),float(points[:,1].max())],"confidence":score if score is None or math.isfinite(score) else None})
    data = {"schema_version":"1.0","source_photo":str(image_path),"image":{"width":image.shape[1],"height":image.shape[0],"coordinate_convention":"Stored pixels; x right, y down; no EXIF rotation, document rotation or unwarping applied.","analysis_image":"analysis_input.png"},"ocr_settings":settings,"package_versions":{p:version(p) for p in ("paddleocr","paddlepaddle","numpy","opencv-python")},"boxes":boxes,"engine_result":native}
    output.mkdir(parents=True, exist_ok=True)
    for filename, pixels in (("analysis_input.png",image),):
        ok, encoded = cv2.imencode(".png",pixels)
        if not ok: raise OSError("Image encoding failed")
        encoded.tofile(output/filename)
    annotated = image.copy()
    for box in boxes:
        pts = np.asarray(box["polygon"],dtype=np.int32)
        cv2.polylines(annotated,[pts],True,(0,0,255),1)
        cv2.putText(annotated,box["id"],tuple(pts[0]),cv2.FONT_HERSHEY_SIMPLEX,.3,(255,0,0),1)
    cv2.imencode(".png",annotated)[1].tofile(output/"ocr_boxes.png")
    save_json(output/"ocr_raw.json",data)
    return data
