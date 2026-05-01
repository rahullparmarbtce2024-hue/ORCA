# 🐋 Orca AI

A production-ready, ChatGPT-like web application powered by local Ollama models or any OpenAI-compatible API. Built with Python (Flask) and a clean dark-themed frontend.

---

## Features

- 💬 Real-time streaming chat (typing effect)
- 🧠 Session-based conversation memory
- 📚 Chat history with sidebar
- 🌙 Dark theme, responsive (mobile + desktop)
- 🔌 Supports **Ollama** (local) and **OpenAI-compatible** APIs
- ⚡ Lightweight — runs on low-RAM machines with `tinyllama`
- 🛑 Stop generation mid-stream
- ✍️ Markdown rendering (code blocks, headers, lists, etc.)

---

## Project Structure

```
orca/
├── app.py              # Flask backend — all API routes
├── requirements.txt    # Python dependencies (only 2!)
├── templates/
│   └── index.html      # Main HTML page
└── static/
    ├── style.css       # Dark theme styles
    └── script.js       # Frontend chat logic
```

---

## Quick Start (Local)

### 1. Install Python dependencies

```bash
cd orca
pip install -r requirements.txt
```

### 2. Set up Ollama (for local AI)

```bash
# Install Ollama from https://ollama.com
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (tinyllama is fast, ~637MB)
ollama pull tinyllama

# Start Ollama (runs on port 11434)
ollama serve
```

### 3. Run Orca

```bash
python app.py
```

Open your browser at: **http://localhost:5000**

---

## Configuration

Edit the `CONFIG` dict near the top of `app.py`:

```python
CONFIG = {
    "provider": "ollama",           # "ollama" or "openai"
    "ollama_model": "tinyllama",    # or "llama3", "mistral", "phi3", etc.
    "openai_api_key": "",           # Your API key if using OpenAI
    "openai_model": "gpt-3.5-turbo",
    "openai_url": "https://api.openai.com/v1/chat/completions",
}
```

### Use a different local model

```bash
ollama pull llama3       # Better quality, ~4GB
ollama pull mistral      # Great balance, ~4GB
ollama pull phi3         # Small and capable, ~2GB
```

Then update `"ollama_model": "llama3"` in `app.py`.

### Use OpenAI instead of Ollama

```python
CONFIG = {
    "provider": "openai",
    "openai_api_key": "sk-your-key-here",
    "openai_model": "gpt-4o",
}
```

### Use any OpenAI-compatible endpoint

Change `openai_url` to point to any compatible server (Together AI, Groq, LM Studio, Ollama's OpenAI-compatible mode, etc.):

```python
"openai_url": "http://localhost:11434/v1/chat/completions",  # Ollama's OpenAI endpoint
"openai_url": "https://api.groq.com/openai/v1/chat/completions",
```

---

## Deploy Online

### Render (Free tier)

1. Push the project to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Set:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `python app.py`
4. Add environment variable: `SECRET_KEY=your-random-secret`
5. Done — Render gives you a public URL

> Note: Ollama won't be available on Render. Use the `openai` provider with an external API key, or run Ollama on a separate server.

### Railway

```bash
# Install Railway CLI
npm i -g @railway/cli
railway login
railway init
railway up
```

### VPS (Ubuntu)

```bash
# Install dependencies
sudo apt update && sudo apt install python3-pip nginx -y
pip install -r requirements.txt gunicorn

# Run with Gunicorn (production WSGI server)
gunicorn -w 2 -b 0.0.0.0:5000 app:app

# Optional: set up Nginx as a reverse proxy
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the main chat UI |
| `/chat` | POST | Send message, returns SSE stream |
| `/history` | GET | List all chats for session |
| `/history/<chat_id>` | GET | Get full messages for a chat |
| `/history/<chat_id>` | DELETE | Delete a chat |
| `/config` | GET | Returns current provider/model info |

### POST /chat

```json
{
  "message": "Explain recursion",
  "chat_id": "optional-existing-chat-id"
}
```

Returns: `text/event-stream` with events:
- `{"type": "meta", "chat_id": "..."}` — chat ID confirmed
- `{"type": "token", "content": "..."}` — streamed token
- `{"type": "done", "title": "..."}` — generation complete

---

## Production Notes

- **Session storage** is in-memory by default — chats are lost on restart. For persistence, replace `chat_sessions` dict with Redis or SQLite.
- **Secret key** — change `app.secret_key` in `app.py` before deploying.
- **HTTPS** — use Nginx or a platform like Render/Railway that handles SSL automatically.
- **Rate limiting** — consider adding `flask-limiter` for public deployments.

---

## License

MIT — use freely, modify, deploy.
