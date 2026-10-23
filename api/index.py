import json

from flask import Flask, jsonify, request

app = Flask(__name__)

MAX_TEXT_LENGTH = 5000


@app.after_request
def add_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def translate_text(text, target, source, engine):
    if engine == "openai":
        from openai_translate import OpenAITranslate
        src = "detect" if source in ("", "auto", "detect") else source
        return OpenAITranslate().translate(text, target=target, source=src)
    from deepl_free import DeepL
    src = "auto" if source in ("", "auto", "detect") else source
    return DeepL().translate(text, target=target, source=src)


def body():
    return request.get_json(silent=True) or {}


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "translate-api", "engines": ["deepl", "openai"], "versions": {"openai-translate": "1.0.2", "deepl-free": "1.0.0"}})


@app.route("/api/translate", methods=["GET", "POST", "OPTIONS"])
def translate():
    if request.method == "OPTIONS":
        return "", 204
    if request.method == "GET":
        return jsonify({"ok": True, "endpoint": "translate", "method": "POST", "body": {"text": "Hello world", "target": "ar", "source": "auto", "engine": "deepl"}, "engines": ["deepl", "openai"]})
    data = body()
    text = str(data.get("text") or "").strip()
    target = str(data.get("target") or "en").strip().lower()
    source = str(data.get("source") or "auto").strip().lower()
    engine = str(data.get("engine") or "deepl").strip().lower()
    if not text:
        return jsonify({"ok": False, "error": "text is required"}), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({"ok": False, "error": f"text exceeds {MAX_TEXT_LENGTH} characters"}), 400
    if engine not in ("deepl", "openai"):
        return jsonify({"ok": False, "error": "engine must be deepl or openai"}), 400
    try:
        result = translate_text(text, target, source, engine)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 502
    return jsonify({"ok": True, "engine": engine, "source": source, "target": target, "text": text, "translation": result})


@app.route("/api/detect", methods=["POST", "OPTIONS"])
def detect():
    if request.method == "OPTIONS":
        return "", 204
    data = body()
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text is required"}), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({"ok": False, "error": f"text exceeds {MAX_TEXT_LENGTH} characters"}), 400
    try:
        from deepl_free import DeepL
        detected = DeepL().detect(text)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 502
    return jsonify({"ok": True, "text": text, "detected_source_language": detected})


@app.route("/api/languages", methods=["GET"])
def languages():
    try:
        from deepl_free import DeepL
        langs = DeepL().languages()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 502
    response = jsonify({"ok": True, "count": len(langs), "languages": langs})
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


if __name__ == "__main__":
    app.run(debug=True)
