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
    payload = {"text": text, "sourceLanguageCode": source, "targetLanguageCode": target}
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "OAI-Device-Id": s.cookies.get("oai-did", ""), "OAI-Session-Id": str(uuid.uuid4()), "OpenAI-Sentinel-Chat-Requirements-Token": t._token, "OpenAI-Sentinel-Proof-Token": t._proof}
    r = s.post(OpenAITranslate.BASE + "/backend-anon/translate/stream", json=payload, headers=headers, timeout=90)
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


OPENCODE_TARBALL = "https://github.com/sst/opencode/releases/download/v1.18.31/opencode-linux-x64.tar.gz"


def opencode_bin():
    import os
    from pathlib import Path

    bundled = Path(__file__).resolve().parent.parent / "bin" / "opencode"
    if bundled.exists():
        return str(bundled)
    cached = Path("/tmp/opencode-bin/opencode")
    if cached.exists():
        return str(cached)
    import tarfile
    import urllib.request

    cached.parent.mkdir(parents=True, exist_ok=True)
    archive = "/tmp/opencode-bin/oc.tar.gz"
    urllib.request.urlretrieve(OPENCODE_TARBALL, archive)
    with tarfile.open(archive) as tf:
        tf.extractall("/tmp/opencode-bin")
    os.chmod(cached, 0o755)
    return str(cached)


def chat_opencode(prompt: str) -> str:
    import os
    import subprocess
    from pathlib import Path

    env = dict(os.environ)
    bin_dir = str(Path(opencode_bin()).resolve().parent)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    timeout = 900
    if env.get("VERCEL"):
        home = "/tmp/opencode-home"
        os.makedirs(home, exist_ok=True)
        env.update({"HOME": home, "XDG_DATA_HOME": home + "/.local/share", "XDG_CONFIG_HOME": home + "/.config", "XDG_CACHE_HOME": home + "/.cache"})
        timeout = 55
    proc = subprocess.run(
        ["opencode", "run", "-m", "opencode/big-pickle", "--format", "json", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    parts = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "error":
            err = event.get("error") or {}
            data = err.get("data") or {}
            raise RuntimeError(data.get("message") or err.get("name") or "opencode error")
        part = event.get("part") or {}
        if event.get("type") == "text" and part.get("type") == "text":
            text = part.get("text") or ""
            if text:
                parts.append(text)
    if not parts and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"opencode exited with {proc.returncode}")
    return "".join(parts)


def chat_cli(messages) -> str:
    if len(messages) == 1:
        return chat_opencode(messages[0].get("content", ""))
    lines = []
    for m in messages:
        role = "Assistant" if m.get("role") == "assistant" else "User"
        lines.append(f"{role}: {m.get('content', '')}")
    return chat_opencode("\n".join(lines))


def chat(messages) -> str:
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
        messages=messages,
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
    return jsonify({"ok": True, "service": "translate-api", "engines": ["deepl", "openai", "google"], "versions": {"openai-translate": "1.0.3", "deepl-free": "1.0.0"}})


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
        return jsonify({"ok": True, "endpoint": "chat", "method": "POST", "body": {"prompt": "Hello", "messages": [{"role": "user", "content": "Hello"}]}, "model": "big-pickle", "provider": "opencode", "via": "opencode CLI installed at build time, Zen API as fallback"})
    data = body()
    messages = data.get("messages")
    if isinstance(messages, list) and messages:
        clean = []
        for m in messages:
            if isinstance(m, dict) and str(m.get("content") or "").strip():
                role = m.get("role") if m.get("role") in ("user", "assistant", "system") else "user"
                clean.append({"role": role, "content": str(m["content"])})
        messages = clean
    else:
        prompt = str(data.get("prompt") or "").strip()
        messages = [{"role": "user", "content": prompt}] if prompt else []
    if not messages:
        return jsonify({"ok": False, "error": "prompt or messages is required"}), 400
    total = sum(len(m["content"]) for m in messages)
    if total > MAX_TEXT_LENGTH * 4:
        return jsonify({"ok": False, "error": "conversation is too long"}), 400
    last_prompt = messages[-1]["content"]
    try:
        reply = chat_cli(messages)
        via = "opencode-cli"
    except Exception:
        try:
            reply = chat(messages)
            via = "zen-api"
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:500]}), 502
    return jsonify({"ok": True, "model": "big-pickle", "via": via, "prompt": last_prompt, "reply": reply})


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

HOME_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Translate API</title>\n<style>\n*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#f2f4f8}\nmain{max-width:820px;margin:0 auto;padding:32px 16px 48px}h1{font-size:28px;margin:0 0 6px}p.sub{color:#9aa4b2;margin:0 0 24px}\n.card{background:#171a21;border:1px solid #262b36;border-radius:16px;padding:20px}\n.row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}.field{flex:1;min-width:140px}\nlabel{display:block;font-size:13px;color:#9aa4b2;margin-bottom:6px}\nselect,textarea,button{width:100%;border-radius:10px;border:1px solid #2c333f;background:#0f1115;color:#f2f4f8;padding:12px;font-size:15px}\ntextarea{min-height:130px;resize:vertical}button{background:#2563eb;border-color:#2563eb;font-weight:600;cursor:pointer}button:disabled{opacity:.6;cursor:wait}\n.out{white-space:pre-wrap;word-break:break-word;background:#0f1115;border:1px solid #2c333f;border-radius:10px;padding:12px;min-height:130px}\n.err{color:#f87171;font-size:14px;min-height:20px;margin-top:10px}code{background:#262b36;padding:2px 6px;border-radius:6px}\n.docs{margin-top:24px;color:#9aa4b2;font-size:14px;line-height:1.9}\n</style>\n</head>\n<body>\n<main>\n<h1>Translate API</h1>\n<p class="sub">Free translation powered by DeepL, ChatGPT Translate and Google Translate, no API key needed</p>\n<div class="card">\n<div class="row">\n<div class="field"><label>Engine</label><select id="engine"><option value="deepl">DeepL</option><option value="openai">ChatGPT Translate</option><option value="google">Google Translate</option></select></div>\n<div class="field"><label>From</label><select id="source"><option value="auto">Auto detect</option><option value="en">English</option><option value="ar">Arabic</option><option value="es">Spanish</option><option value="fr">French</option><option value="de">German</option><option value="it">Italian</option><option value="pt">Portuguese</option><option value="ru">Russian</option><option value="zh">Chinese</option><option value="ja">Japanese</option><option value="ko">Korean</option><option value="tr">Turkish</option></select></div>\n<div class="field"><label>To</label><select id="target"><option value="ar">Arabic</option><option value="en">English</option><option value="es">Spanish</option><option value="fr">French</option><option value="de">German</option><option value="it">Italian</option><option value="pt">Portuguese</option><option value="ru">Russian</option><option value="zh">Chinese</option><option value="ja">Japanese</option><option value="ko">Korean</option><option value="tr">Turkish</option></select></div>\n</div>\n<div class="row"><div class="field"><label>Text</label><textarea id="text" placeholder="Type text to translate"></textarea></div></div>\n<div class="row"><div class="field"><label>Translation</label><div class="out" id="output"></div></div></div>\n<button id="go">Translate</button>\n<div class="err" id="err"></div>\n</div>\n<div class="card" style="margin-top:20px">\n<div class="row"><div class="field"><label>AI Chat, big-pickle</label><textarea id="prompt" placeholder="Ask anything"></textarea></div></div>\n<div class="row"><div class="field"><label>Reply</label><div class="out" id="chatout"></div></div></div>\n<button id="ask">Ask</button>\n<div class="err" id="chaterr"></div>\n</div>\n<div class="docs">\nAPI<br>\n<code>POST /api/translate</code> with <code>{"text":"Hello","target":"ar","source":"auto","engine":"deepl"}</code><br>\n<code>POST /api/chat</code> with <code>{"prompt":"Hello"}</code><br>\n<code>POST /api/detect</code> with <code>{"text":"Bonjour"}</code><br>\n<code>GET /api/languages</code> and <code>GET /api/health</code>\n</div>\n</main>\n<script>\nconst go=document.getElementById(\'go\'),out=document.getElementById(\'output\'),err=document.getElementById(\'err\');\ngo.onclick=async()=>{err.textContent=\'\';out.textContent=\'\';go.disabled=true;go.textContent=\'Translating...\';\ntry{const r=await fetch(\'/api/translate\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({text:document.getElementById(\'text\').value,target:document.getElementById(\'target\').value,source:document.getElementById(\'source\').value,engine:document.getElementById(\'engine\').value})});\nconst d=await r.json();if(!d.ok)throw new Error(d.error||\'failed\');out.textContent=d.translation}catch(e){err.textContent=e.message}\ngo.disabled=false;go.textContent=\'Translate\'};\nconst ask=document.getElementById(\'ask\'),cout=document.getElementById(\'chatout\'),cerr=document.getElementById(\'chaterr\'),history=[];\nask.onclick=async()=>{cerr.textContent=\'\';const q=document.getElementById(\'prompt\').value.trim();if(!q)return;history.push({role:\'user\',content:q});document.getElementById(\'prompt\').value=\'\';ask.disabled=true;ask.textContent=\'Thinking...\';\ntry{const r=await fetch(\'/api/chat\',{method:\'POST\',headers:{\'Content-Type\':\'application/json\'},body:JSON.stringify({messages:history})});\nconst d=await r.json();if(!d.ok)throw new Error(d.error||\'failed\');history.push({role:\'assistant\',content:d.reply});cout.textContent=history.map(m=>(m.role===\'user\'?\'You: \':\'AI: \')+m.content).join(\'\\n\\n\')}catch(e){cerr.textContent=e.message;history.pop()}\nask.disabled=false;ask.textContent=\'Ask\'};\n</script>\n</body>\n</html>\n'


@app.route("/", methods=["GET"])
def home():
    return HOME_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


if __name__ == "__main__":
    app.run(debug=True)
