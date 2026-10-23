# Egyptology Translate API

Free translation API deployed on Vercel, powered by two Python libraries with no API key and no login required

- `openai-translate==1.0.2` for ChatGPT Translate
- `deepl-free==1.0.0` for DeepL
- Google Translate through its free web endpoint, no key needed

## Live endpoints

### Translate

```bash
curl -X POST https://egyptology-api.vercel.app/api/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "target": "ar", "source": "auto", "engine": "deepl"}'
```

```json
{"ok": true, "engine": "deepl", "source": "auto", "target": "ar", "text": "Hello world", "translation": "مرحباً بالعالم"}
```

| Field | Description | Default |
|---|---|---|
| `text` | Text to translate, max 5000 characters | required |
| `target` | Target language code such as `ar`, `en`, `es`, `fr`, `de` | `en` |
| `source` | Source language code, or `auto` | `auto` |
| `engine` | `deepl`, `openai` or `google` | `deepl` |

### AI chat

Free chat powered by the `big-pickle` model on OpenCode Zen, no key needed

```bash
curl -X POST https://egyptology-api.vercel.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
```

```json
{"ok": true, "model": "big-pickle", "prompt": "Hello", "reply": "Hello! How can I help you today?"}
```

The free tier has a shared usage limit, when it is reached the endpoint returns the upstream limit error until the quota resets

### Detect language

```bash
curl -X POST https://egyptology-api.vercel.app/api/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour le monde"}'
```

### Languages

```bash
curl https://egyptology-api.vercel.app/api/languages
```

### Health

```bash
curl https://egyptology-api.vercel.app/api/health
```

Note: chatgpt.com blocks plain datacenter requests, so the `openai` engine retries automatically with a Chrome-impersonated session (curl_cffi) when the first handshake is blocked

## Run locally

```bash
pip install -r requirements.txt
vercel dev
```

## Deploy

This repo is linked to a Vercel project, every push to `main` deploys automatically

## License

MIT
