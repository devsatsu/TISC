"""Local API: JSON/base64 uploads, asynchronous jobs, persistent results."""
import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
import cv2
import numpy as np
from bill_backend import process, ROOT
from ocr_reader import save_json

STORE = ROOT/"API_Results"
POOL = ThreadPoolExecutor(max_workers=1)
JOBS = {}
LOCK = threading.Lock()


def work(identifier, paths):
    try:
        result = process(paths, output_root=STORE/identifier/"analysis")
        result["request_id"] = identifier
        save_json(STORE/identifier/"result.json", result)
        status = result["status"]
    except Exception as exc:
        status = "failed"
        save_json(STORE/identifier/"result.json", {"status":status,"error":str(exc)})
    with LOCK:
        JOBS[identifier] = status


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body):
        raw=json.dumps(body,ensure_ascii=False,allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200,{"status":"ok"})
        identifier=self.path.removeprefix("/bills/")
        if not self.path.startswith("/bills/") or len(identifier)!=32 or any(c not in "0123456789abcdef" for c in identifier):
            return self.reply(404,{"error":"Unknown endpoint"})
        result=STORE/identifier/"result.json"
        if result.exists():
            return self.reply(200,json.loads(result.read_text(encoding="utf-8")))
        with LOCK:
            status=JOBS.get(identifier)
        if status:
            return self.reply(202,{"request_id":identifier,"status":status})
        if (STORE/identifier).exists():
            return self.reply(409,{"status":"interrupted","error":"Server restarted before completion; submit again."})
        self.reply(404,{"error":"Unknown bill"})

    def do_POST(self):
        if self.path!="/bills":
            return self.reply(404,{"error":"Unknown endpoint"})
        with LOCK:
            busy = sum(status == "queued" for status in JOBS.values()) >= 20
        if busy:
            return self.reply(503, {"error":"Queue full; retry later."})
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=40*1024*1024:
                return self.reply(413,{"error":"Request must be at most 40 MB."})
            payload=json.loads(self.rfile.read(length))
            photos=payload["photos"]
            if not isinstance(photos,list) or not 1<=len(photos)<=10:
                raise ValueError("Supply 1 to 10 photos")
            decoded=[]
            for photo in photos:
                data=base64.b64decode(photo["base64"],validate=True)
                if len(data)>10*1024*1024:
                    raise ValueError("Each photo must be at most 10 MB")
                pixels=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION)
                if pixels is None or pixels.shape[0]*pixels.shape[1]>30_000_000:
                    raise ValueError("Unreadable image or image exceeds 30 megapixels")
                decoded.append(data)
            identifier=uuid4().hex
            folder=STORE/identifier
            folder.mkdir(parents=True)
            paths=[]
            for i,data in enumerate(decoded):
                path=folder/f"photo_{i+1}.image"
                path.write_bytes(data)
                paths.append(path)
            with LOCK:
                JOBS[identifier]="queued"
            POOL.submit(work,identifier,paths)
            self.reply(202,{"request_id":identifier,"status":"queued","result_url":f"/bills/{identifier}"})
        except (ValueError,KeyError,TypeError) as exc:
            self.reply(400,{"error":str(exc)})


if __name__=="__main__":
    print("Local backend: http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1",8000),Handler).serve_forever()
