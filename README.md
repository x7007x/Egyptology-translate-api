# Translate API

Free translation API deployed on Vercel, powered by two Python libraries with no API key and no login required

- `openai-translate==1.0.2` for ChatGPT Translate
- `deepl-free==1.0.0` for DeepL

## Live endpoints

### Translate

```bash
curl -X POST https://translate-api-smoky.vercel.app/api/translate \
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
| `engine` | `deepl` or `openai` | `deepl` |

### Detect language

```bash
curl -X POST https://translate-api-smoky.vercel.app/api/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour le monde"}'
```

### Languages

```bash
curl https://translate-api-smoky.vercel.app/api/languages
```

### Health

```bash
curl https://translate-api-smoky.vercel.app/api/health
```

Note: the `openai` engine talks to chatgpt.com, which sometimes blocks datacenter IPs, so on Vercel it can return an error while the same code works from a local machine. The `deepl` engine works on Vercel with no restrictions

## Run locally

```bash
pip install -r requirements.txt
vercel dev
```

## Deploy

This repo is linked to a Vercel project, every push to `main` deploys automatically

## License

MIT
