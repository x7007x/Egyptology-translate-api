import json
from http.server import BaseHTTPRequestHandler

MAX_TEXT_LENGTH = 5000


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"ok": False, "error": "invalid JSON body"})
        text = str(data.get("text") or "").strip()
        if not text:
            return self._send(400, {"ok": False, "error": "text is required"})
        if len(text) > MAX_TEXT_LENGTH:
            return self._send(400, {"ok": False, "error": f"text exceeds {MAX_TEXT_LENGTH} characters"})
        try:
            from deepl_free import DeepL
            detected = DeepL().detect(text)
        except Exception as e:
            return self._send(502, {"ok": False, "error": str(e)[:300]})
        self._send(200, {"ok": True, "text": text, "detected_source_language": detected})

    def log_message(self, format, *args):
        pass
