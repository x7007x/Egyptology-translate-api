import json
from http.server import BaseHTTPRequestHandler

MAX_TEXT_LENGTH = 5000


def translate_text(text, target, source, engine):
    if engine == "openai":
        from openai_translate import OpenAITranslate
        src = "detect" if source in ("", "auto", "detect") else source
        return OpenAITranslate().translate(text, target=target, source=src)
    from deepl_free import DeepL
    src = "auto" if source in ("", "auto", "detect") else source
    return DeepL().translate(text, target=target, source=src)


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        self._send(200, {"ok": True, "endpoint": "translate", "method": "POST", "body": {"text": "Hello world", "target": "ar", "source": "auto", "engine": "deepl"}, "engines": ["deepl", "openai"]})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send(400, {"ok": False, "error": "invalid JSON body"})
        text = str(data.get("text") or "").strip()
        target = str(data.get("target") or "en").strip().lower()
        source = str(data.get("source") or "auto").strip().lower()
        engine = str(data.get("engine") or "deepl").strip().lower()
        if not text:
            return self._send(400, {"ok": False, "error": "text is required"})
        if len(text) > MAX_TEXT_LENGTH:
            return self._send(400, {"ok": False, "error": f"text exceeds {MAX_TEXT_LENGTH} characters"})
        if engine not in ("deepl", "openai"):
            return self._send(400, {"ok": False, "error": "engine must be deepl or openai"})
        try:
            result = translate_text(text, target, source, engine)
        except Exception as e:
            return self._send(502, {"ok": False, "error": str(e)[:300]})
        self._send(200, {"ok": True, "engine": engine, "source": source, "target": target, "text": text, "translation": result})

    def log_message(self, format, *args):
        pass
