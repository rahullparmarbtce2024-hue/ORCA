"""
Orca AI - ChatGPT-like web application
Supports local Ollama models and OpenAI-compatible external APIs
"""

import os
import json
import uuid
import time
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, Response, stream_with_context

app = Flask(__name__)
app.secret_key = "orca-secret-key-change-in-production"

# ─── Configuration ────────────────────────────────────────────────────────────

import os

CONFIG = {
    "provider": "openai", 

    "ollama_url": "http://localhost:11434/api/generate",
    "ollama_model": "tinyllama",

    "openai_url": "https://api.openai.com/v1/chat/completions",
    "openai_api_key": os.getenv("OPENAI_API_KEY"), 
    "openai_model": "llama3-8b-8192",

    "max_history": 20,
    "timeout": 60,
}
# In-memory storage for chat sessions (use Redis/DB in production)
chat_sessions = {}

# ─── Helper Functions ──────────────────────────────────────────────────────────

def get_session_id():
    """Get or create a session ID for the current user."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]

def get_chat_history(session_id, chat_id):
    """Retrieve chat history for a given session and chat."""
    return chat_sessions.get(session_id, {}).get(chat_id, {
        "id": chat_id,
        "title": "New Chat",
        "messages": [],
        "created_at": datetime.now().isoformat()
    })

def save_message(session_id, chat_id, role, content):
    """Save a message to the chat history."""
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
    chat["messages"].append({"role": role, "content": content, "timestamp": time.time()})

    # Auto-title the chat from the first user message
    if role == "user" and chat["title"] == "New Chat":
        chat["title"] = content[:40] + ("..." if len(content) > 40 else "")

    # Trim history to avoid memory bloat
    if len(chat["messages"]) > CONFIG["max_history"]:
        chat["messages"] = chat["messages"][-CONFIG["max_history"]:]

def build_context(messages):
    """Build a simple text context from message history for Ollama."""
    context = ""
    for msg in messages[-10:]:  # Use last 10 messages for context
        prefix = "User" if msg["role"] == "user" else "Assistant"
        context += f"{prefix}: {msg['content']}\n"
    return context

# ─── AI Streaming Functions ────────────────────────────────────────────────────

def stream_ollama(prompt, history):
    """Stream response from local Ollama instance."""
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
                try:
                    data = json.loads(line.decode("utf-8"))
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue

    except requests.exceptions.ConnectionError:
        yield "\n\n⚠️ **Cannot connect to Ollama.** Make sure Ollama is running:\n```\nollama serve\n```"
    except requests.exceptions.Timeout:
        yield "\n\n⚠️ **Request timed out.** The model may be overloaded or too large for this system."
    except Exception as e:
        yield f"\n\n⚠️ **Error:** {str(e)}"

def stream_openai(prompt, history):
    """Stream response from OpenAI-compatible API."""
    messages = [{"role": "system", "content": "You are Orca, a helpful AI assistant."}]
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {CONFIG['openai_api_key']}",
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
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    data = json.loads(line)
                    token = data["choices"][0]["delta"].get("content", "")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError):
                    continue

    except requests.exceptions.ConnectionError:
        yield "\n\n⚠️ **Cannot connect to the API endpoint.** Check your URL and network connection."
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            yield "\n\n⚠️ **Authentication failed.** Check your API key."
        else:
            yield f"\n\n⚠️ **HTTP Error {e.response.status_code}:** {e.response.text}"
    except Exception as e:
        yield f"\n\n⚠️ **Error:** {str(e)}"

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main chat interface."""
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    """
    Handle chat messages with streaming response.
    Expects JSON: { "message": str, "chat_id": str }
    Returns: Server-Sent Events stream
    """
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' field"}), 400

    user_message = data["message"].strip()
    chat_id = data.get("chat_id") or str(uuid.uuid4())
    session_id = get_session_id()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # Get existing history before saving new message
    chat = get_chat_history(session_id, chat_id)
    history = chat["messages"].copy()

    # Save the user's message
    save_message(session_id, chat_id, "user", user_message)

    # Collect assistant response for saving
    full_response = []

    def generate():
        # Yield the chat_id first so the frontend knows which chat to update
        yield f"data: {json.dumps({'type': 'meta', 'chat_id': chat_id})}\n\n"

        # Choose the right streaming provider
        streamer = stream_ollama if CONFIG["provider"] == "ollama" else stream_openai

        for token in streamer(user_message, history):
            full_response.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        # Save the complete assistant response
        complete = "".join(full_response)
        save_message(session_id, chat_id, "assistant", complete)

        # Signal completion with updated chat title
        updated_chat = chat_sessions.get(session_id, {}).get(chat_id, {})
        yield f"data: {json.dumps({'type': 'done', 'title': updated_chat.get('title', 'New Chat')})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable Nginx buffering for streaming
        }
    )

@app.route("/history", methods=["GET"])
def history():
    """
    Return list of all chats for the current session.
    Returns: JSON array of chat objects
    """
    session_id = get_session_id()
    chats = chat_sessions.get(session_id, {})

    # Return chats sorted by creation time (newest first)
    chat_list = sorted(
        [{"id": c["id"], "title": c["title"], "created_at": c["created_at"]}
         for c in chats.values()],
        key=lambda x: x["created_at"],
        reverse=True
    )
    return jsonify(chat_list)

@app.route("/history/<chat_id>", methods=["GET"])
def get_chat(chat_id):
    """Return full message history for a specific chat."""
    session_id = get_session_id()
    chat = get_chat_history(session_id, chat_id)
    return jsonify(chat)

@app.route("/history/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    """Delete a specific chat from history."""
    session_id = get_session_id()
    if session_id in chat_sessions and chat_id in chat_sessions[session_id]:
        del chat_sessions[session_id][chat_id]
    return jsonify({"success": True})

@app.route("/config", methods=["GET"])
def get_config():
    """Return safe (non-sensitive) config info to the frontend."""
    return jsonify({
        "provider": CONFIG["provider"],
        "model": CONFIG["ollama_model"] if CONFIG["provider"] == "ollama" else CONFIG["openai_model"]
    })

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🐋 Orca AI is starting...")
    print(f"   Provider : {CONFIG['provider']}")
    print(f"   Model    : {CONFIG['ollama_model'] if CONFIG['provider'] == 'ollama' else CONFIG['openai_model']}")
    print(f"   URL      : http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
