# Egyptology Translate API

Free translation API deployed on Vercel, powered by two Python libraries with no API key and no login required

- `openai-translate==1.0.3` for ChatGPT Translate
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

Free chat powered by the `big-pickle` model through the real OpenCode client, no key needed. The Vercel build installs the `opencode` CLI into the deployment and the endpoint runs it for each chat, with the OpenCode Zen API as a fallback. Multi-turn chats are supported by sending the full history

```bash
curl -X POST https://egyptology-api.vercel.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Hello"}'
```

```bash
curl -X POST https://egyptology-api.vercel.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi, how can I help?"}, {"role": "user", "content": "Tell me a joke"}]}'
```

```json
{"ok": true, "model": "big-pickle", "via": "opencode-cli", "prompt": "Hello", "reply": "Hello! How can I help you today?"}

The model can call tools while it works (bash, read, write, edit, search and more) inside a sandbox. Every call it makes comes back in `tool_calls` with its name, status, input and output:

```json
{"tool": "bash", "status": "completed", "input": {"command": "echo hi"}, "output": "hi"}
```
```

Chats run through the installed OpenCode client. If that path ever fails, the endpoint falls back to the Zen API and returns its error as-is

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
