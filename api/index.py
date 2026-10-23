import json
import secrets

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


def translate_openai_cffi(text, target, source):
    import uuid

    from curl_cffi import requests as creq
    from openai_translate import OpenAITranslate

    t = OpenAITranslate()
    s = creq.Session(impersonate="chrome")
    s.headers.update({"User-Agent": OpenAITranslate.UA, "Origin": OpenAITranslate.BASE, "Referer": OpenAITranslate.BASE + "/translate/"})
    t.s = s
    t._handshake()
    payload = {"request": {"includeDetectedLanguage": source == "detect", "sourceLanguageCode": source, "sourceLanguageLabel": OpenAITranslate.LABELS.get(source, source), "targetLanguageCode": target, "targetLanguageLabel": OpenAITranslate.LABELS.get(target, target), "text": text, "pipeline": "latency-optimized"}, "dedicatedRequest": None, "sentinel": {"chatReqToken": t._token, "chatReqPrepareToken": t._prepare_token, "turnstileToken": None, "proofToken": t._proof}}
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "OAI-Language": "en-US", "OAI-Device-Id": s.cookies.get("oai-did", ""), "x-openai-web-frontend": "core_web", "OAI-Client-Version": "prod-c8f39f744fd82e629b912bf379c8c9837ab5ccde", "OAI-Client-Build-Number": "12327112", "OAI-Session-Id": str(uuid.uuid4())}
    r = s.post(OpenAITranslate.BASE + "/translate/stream", json=payload, headers=headers, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"translate failed ({r.status_code})")
    out = []
    for line in r.text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            out.append(json.loads(data).get("delta", ""))
        except ValueError:
            pass
    result = "".join(out)
    if not result:
        raise RuntimeError("empty translation response")
    return result


def translate_openai(text, target, source):
    from openai_translate import OpenAITranslate

    last = None
    for attempt in range(3):
        try:
            if attempt == 0:
                return OpenAITranslate().translate(text, target=target, source=source)
            return translate_openai_cffi(text, target, source)
        except Exception as e:
            last = e
    raise RuntimeError(f"openai engine failed after retries: {str(last)[:200]}")


GOOGLE_LANG_MAP = {"zh": "zh-CN", "zh-hans": "zh-CN", "zh-hant": "zh-TW", "he": "iw", "nb": "no"}


def google_code(code):
    return GOOGLE_LANG_MAP.get(code.strip().lower(), code.strip().lower())


def google_once(text, target, source, session):
    r = session.get("https://translate.googleapis.com/translate_a/single", params={"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"google translate failed ({r.status_code})")
    data = r.json()
    out = "".join(seg[0] for seg in data[0] if seg and seg[0])
    if not out:
        raise RuntimeError("empty translation response")
    return out


def translate_google(text, target, source):
    tgt = google_code(target)
    src = "auto" if source in ("", "auto", "detect") else google_code(source)
    last = None
    for attempt in range(3):
        try:
            if attempt == 0:
                import requests
                s = requests.Session()
                s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"})
                return google_once(text, tgt, src, s)
            from curl_cffi import requests as creq
            return google_once(text, tgt, src, creq.Session(impersonate="chrome"))
        except Exception as e:
            last = e
    raise RuntimeError(f"google engine failed after retries: {str(last)[:200]}")


def translate_text(text, target, source, engine):
    if engine == "openai":
        src = "detect" if source in ("", "auto", "detect") else source
        return translate_openai(text, target, src)
    if engine == "google":
        return translate_google(text, target, source)
    from deepl_free import DeepL
    src = "auto" if source in ("", "auto", "detect") else source
    return DeepL().translate(text, target=target, source=src)


def chat(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(
        base_url="https://opencode.ai/zen/v1",
        api_key="public",
        default_headers={
            "User-Agent": "opencode/1.18.31",
            "x-opencode-session": "ses_" + secrets.token_hex(13),
        },
        timeout=120,
    )
    stream = client.chat.completions.create(
        model="big-pickle",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        tools=[
            {"type": "function", "function": {"name": "bash", "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "read", "parameters": {"type": "object", "properties": {}}}},
        ],
    )
    parts = []
    for chunk in stream:
        if not chunk.choices:
            continue
        text = chunk.choices[0].delta.content or ""
        if text:
            parts.append(text)
    return "".join(parts)


def body():
    return request.get_json(silent=True) or {}


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "translate-api", "engines": ["deepl", "openai", "google"], "versions": {"openai-translate": "1.0.2", "deepl-free": "1.0.0"}})


@app.route("/api/translate", methods=["GET", "POST", "OPTIONS"])
def translate():
    if request.method == "OPTIONS":
        return "", 204
    if request.method == "GET":
        return jsonify({"ok": True, "endpoint": "translate", "method": "POST", "body": {"text": "Hello world", "target": "ar", "source": "auto", "engine": "deepl"}, "engines": ["deepl", "openai", "google"]})
    data = body()
    text = str(data.get("text") or "").strip()
    target = str(data.get("target") or "en").strip().lower()
    source = str(data.get("source") or "auto").strip().lower()
    engine = str(data.get("engine") or "deepl").strip().lower()
    if not text:
        return jsonify({"ok": False, "error": "text is required"}), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({"ok": False, "error": f"text exceeds {MAX_TEXT_LENGTH} characters"}), 400
    if engine not in ("deepl", "openai", "google"):
        return jsonify({"ok": False, "error": "engine must be deepl, openai or google"}), 400
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


@app.route("/api/chat", methods=["GET", "POST", "OPTIONS"])
def ai_chat():
    if request.method == "OPTIONS":
        return "", 204
    if request.method == "GET":
        return jsonify({"ok": True, "endpoint": "chat", "method": "POST", "body": {"prompt": "Hello"}, "model": "big-pickle", "provider": "opencode.ai/zen"})
    data = body()
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "prompt is required"}), 400
    if len(prompt) > MAX_TEXT_LENGTH:
        return jsonify({"ok": False, "error": f"prompt exceeds {MAX_TEXT_LENGTH} characters"}), 400
    try:
        reply = chat(prompt)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]}), 502
    return jsonify({"ok": True, "model": "big-pickle", "prompt": prompt, "reply": reply})


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

HOME_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Translate API</title>\n<style>\n*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#f2f4f8}\nmain{max-width:820px;margin:0 auto;padding:32px 16px 48px}h1{font-size:28px;margin:0 0 6px}p.sub{color:#9aa4b2;margin:0 0 24px}\n.card{background:#171a21;border:1px solid #262b36;border-radius:16px;padding:20px}\n.row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}.field{flex:1;min-width:140px}\nlabel{display:block;font-size:13px;color:#9aa4b2;margin-bottom:6px}\nselect,textarea,button{width:100%;border-radius:10px;border:1px solid #2c333f;background:#0f1115;color:#f2f4f8;padding:12px;font-size:15px}\ntextarea{min-height:130px;resize:vertical}button{background:#2563eb;border-color:#2563eb;font-weight:600;cursor:pointer}button:disabled{opacity:.6;cursor:wait}\n.out{white-space:pre-wrap;word-break:break-word;background:#0f1115;border:1px solid #2c333f;border-radius:10px;padding:12px;min-height:130px}\n.err{color:#f87171;font-size:14px;min-height:20px;margin-top:10px}code{background:#262b36;padding:2px 6px;border-radius:6px}\n.docs{margin-top:24px;color:#9aa4b2;font-size:14px;line-height:1.9}\n</style>\n</head>\n<body>\n<main>\n<h1>Translate API</h1>\n<p class="sub">Free translation powered by DeepL, ChatGPT Translate and Google Translate, no API key needed</p>\n<div class="card">\n<div class="row">\n<div class="field"><label>Engine</label><select id="engine"><option value="deepl">DeepL</option><option value="openai">ChatGPT Translate</option><option value="google">Google Translate</option></select></div>\n<div class="field"><label>From</label><select id="source"><option value="auto">Auto detect</option><option value="en">English</option><option value="ar">Arabic</option><option value="es">Spanish</option><option value="fr">French</option><option value="de">German</option><option value="it">Italian</option><option value="pt">Portuguese</option><option value="ru">Russian</option><option value="zh">Chinese</option><option value="ja">Japanese</option><option value="ko">Korean</option><option value="tr">Turkish</option></select></div>\n<div class="field"><label>To</label><select id="target"><option value="ar">Arabic</option><option value="en">English</option><option value="es">Spanish</option><option value="fr">French</option><option value="de">German</option><option value="it">Italian</option><option value="pt">Portuguese</option><option value="ru">Russian</option><option value="zh">Chinese</option><option value="ja">Japanese</option><option value="ko">Korean</option><option value="tr">Turkish</option></select></div>\n</div>\n<div class="row"><div class="field"><label>Text</label><textarea id="text" placeholder="Type text to translate"></textarea></div></div>\n<div class="row"><div class="field"><label>Translation</label><div class="out" id="output"></div></div></div>\n<button id="go">Translate</button>\n<div class="err" id="err"></div>\n</div>\n<div class="card" style="margin-top:20px">\n<div class="row"><div class="field"><label>AI Chat, big-pickle</label><textarea id="prompt" placeholder="Ask anything"></textarea></div></div>\n<div class="row"><div class="field"><label>Reply</label><div class="out" id="chatout"></div></div></div>\n<button id="ask">Ask</button>\n<div class="err" id="chaterr"></div>\n</div>\n<div class="docs">\nAPI<br>\n<code>POST /api/translate</code> with <code>{"text":"Hello","target":"ar","source":"auto","engine":"deepl"}</code><br>\n<code>POST /api/chat</code> with <code>{"prompt":"Hello"}</code><br>\n<code>POST /api/detect</code> with <code>{"text":"Bonjour"}</code><br>\n<code>GET /api/languages</code> and <code>GET /api/health</code>\n</div>\n</main>\n<script>\nconst go=document.getElementById(\'go\'),out=document.getElementById(\'output\'),err=document.getElementById(\'err\');\ngo.onclick=async()=>{err.textContent=\'\';out.textContent=\'\';go.disabled=true;go.textContent=\'Translating...\';\ntry{const r=await fetch(\'/api/translate\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({text:document.getElementById(\'text\').value,target:document.getElementById(\'target\').value,source:document.getElementById(\'source\').value,engine:document.getElementById(\'engine\').value})});\nconst d=await r.json();if(!d.ok)throw new Error(d.error||\'failed\');out.textContent=d.translation}catch(e){err.textContent=e.message}\ngo.disabled=false;go.textContent=\'Translate\'};\nconst ask=document.getElementById(\'ask\'),cout=document.getElementById(\'chatout\'),cerr=document.getElementById(\'chaterr\');\nask.onclick=async()=>{cerr.textContent=\'\';cout.textContent=\'\';ask.disabled=true;ask.textContent=\'Thinking...\';\ntry{const r=await fetch(\'/api/chat\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({prompt:document.getElementById(\'prompt\').value})});\nconst d=await r.json();if(!d.ok)throw new Error(d.error||\'failed\');cout.textContent=d.reply}catch(e){cerr.textContent=e.message}\nask.disabled=false;ask.textContent=\'Ask\'};\n</script>\n</body>\n</html>\n'


@app.route("/", methods=["GET"])
def home():
    return HOME_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


if __name__ == "__main__":
    app.run(debug=True)
