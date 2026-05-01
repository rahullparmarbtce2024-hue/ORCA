"""
Orca AI - ChatGPT-like web application
Now FIXED for Groq API + improved stability
"""

import os
import json
import uuid
import time
import requests
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, Response, stream_with_context
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

# Logging
logging.basicConfig(level=logging.INFO)

# ─── Configuration ─────────────────────────────────────────

CONFIG = {
    "provider": "openai",  # "ollama" or "openai"

    # Ollama
    "ollama_url": "http://localhost:11434/api/generate",
    "ollama_model": "tinyllama",

    # Groq (OpenAI-compatible)
    "openai_url": "https://api.groq.com/openai/v1/chat/completions",
    "openai_api_key": os.getenv("GROQ_API_KEY"),
    "openai_model": "mixtral-8x7b-32768",

    "max_history": 20,
    "timeout": 60,
}

chat_sessions = {}

# ─── Helpers ───────────────────────────────────────────────

def get_session_id():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]

def get_chat_history(session_id, chat_id):
    return chat_sessions.get(session_id, {}).get(chat_id, {
        "id": chat_id,
        "title": "New Chat",
        "messages": [],
        "created_at": datetime.now().isoformat()
    })

def save_message(session_id, chat_id, role, content):
    if session_id not in chat_sessions:
        chat_sessions[session_id] = {}

    if chat_id not in chat_sessions[session_id]:
        chat_sessions[session_id][chat_id] = {
            "id": chat_id,
            "title": "New Chat",
            "messages": [],
            "created_at": datetime.now().isoformat()
        }

    chat = chat_sessions[session_id][chat_id]
    chat["messages"].append({
        "role": role,
        "content": content,
        "timestamp": time.time()
    })

    if role == "user" and chat["title"] == "New Chat":
        chat["title"] = content[:40]

    if len(chat["messages"]) > CONFIG["max_history"]:
        chat["messages"] = chat["messages"][-CONFIG["max_history"]:]

def build_context(messages):
    context = ""
    for msg in messages[-10:]:
        prefix = "User" if msg["role"] == "user" else "Assistant"
        context += f"{prefix}: {msg['content']}\n"
    return context

# ─── Streaming Functions ───────────────────────────────────

def stream_ollama(prompt, history):
    context = build_context(history)
    full_prompt = f"{context}User: {prompt}\nAssistant:"

    payload = {
        "model": CONFIG["ollama_model"],
        "prompt": full_prompt,
        "stream": True
    }

    try:
        response = requests.post(
            CONFIG["ollama_url"],
            json=payload,
            stream=True,
            timeout=CONFIG["timeout"]
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                data = json.loads(line.decode("utf-8"))
                token = data.get("response", "")
                if token:
                    yield token
                if data.get("done"):
                    break

    except Exception as e:
        yield f"\n\n⚠️ Ollama Error: {str(e)}"

def stream_openai(prompt, history):
    api_key = CONFIG["openai_api_key"]

    if not api_key:
        yield "\n\n⚠️ GROQ_API_KEY not found. Check your .env file."
        return

    messages = [{"role": "system", "content": "You are Orca, a helpful AI assistant."}]
    messages += history[-10:]
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": CONFIG["openai_model"],
        "messages": messages,
        "stream": True
    }

    try:
        response = requests.post(
            CONFIG["openai_url"],
            headers=headers,
            json=payload,
            stream=True,
            timeout=CONFIG["timeout"]
        )

        if response.status_code == 401:
            yield "\n\n⚠️ Authentication failed. Check your GROQ API key."
            return

        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")

                if line.startswith("data: "):
                    line = line[6:]

                if line.strip() == "[DONE]":
                    break

                try:
                    data = json.loads(line)
                    token = data["choices"][0]["delta"].get("content", "")
                    if token:
                        yield token
                except:
                    continue

    except requests.exceptions.ConnectionError:
        yield "\n\n⚠️ Cannot connect to Groq API."
    except Exception as e:
        yield f"\n\n⚠️ Error: {str(e)}"

# ─── Routes ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({"error": "Missing message"}), 400

    user_message = data["message"].strip()
    chat_id = data.get("chat_id") or str(uuid.uuid4())
    session_id = get_session_id()

    history = get_chat_history(session_id, chat_id)["messages"].copy()

    save_message(session_id, chat_id, "user", user_message)

    full_response = []

    def generate():
        yield f"data: {json.dumps({'type': 'meta', 'chat_id': chat_id})}\n\n"

        streamer = stream_ollama if CONFIG["provider"] == "ollama" else stream_openai

        for token in streamer(user_message, history):
            full_response.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        complete = "".join(full_response)
        save_message(session_id, chat_id, "assistant", complete)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")

@app.route("/history", methods=["GET"])
def history():
    session_id = get_session_id()
    chats = chat_sessions.get(session_id, {})

    return jsonify([
        {"id": c["id"], "title": c["title"]}
        for c in chats.values()
    ])

@app.route("/history/<chat_id>", methods=["GET"])
def get_chat(chat_id):
    session_id = get_session_id()
    return jsonify(get_chat_history(session_id, chat_id))

@app.route("/history/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    session_id = get_session_id()
    if session_id in chat_sessions and chat_id in chat_sessions[session_id]:
        del chat_sessions[session_id][chat_id]
    return jsonify({"success": True})

# ─── Run ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 Orca AI running at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
