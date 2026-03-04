#!/usr/bin/env python3
"""
ChatGPT Conversation Manager – Flask backend
Run: python app.py
Then open: http://localhost:5000
"""

from flask import Flask, jsonify, request, render_template
import requests
import os

app = Flask(__name__)

BASE_URL = "https://chatgpt.com/backend-api"

# Disable system proxy detection — prevents macOS _scproxy crash after fork
http = requests.Session()
http.trust_env = False


def chatgpt_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://chatgpt.com/",
    }


@app.route("/")
def index():
    token = request.args.get("token", "")
    return render_template("index.html", prefill_token=token)


PAGE_SIZE = 50

@app.route("/api/conversations")
def get_conversations():
    token  = request.args.get("token", "").strip()
    offset = int(request.args.get("offset", 0))
    if not token:
        return jsonify({"error": "No token provided"}), 400

    try:
        resp = http.get(
            f"{BASE_URL}/conversations",
            headers=chatgpt_headers(token),
            params={"offset": offset, "limit": PAGE_SIZE, "order": "updated"},
            timeout=30,
        )
        if resp.status_code == 401:
            return jsonify({"error": "Invalid or expired token"}), 401
        resp.raise_for_status()

        data  = resp.json()
        items = data.get("items", [])
        total = data.get("total", 0)

        return jsonify({
            "conversations": items,
            "total":         total,
            "offset":        offset,
            "page_size":     PAGE_SIZE,
            "has_more":      (offset + len(items)) < total,
        })

    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/delete", methods=["POST"])
def delete_conversations():
    body = request.get_json(force=True)
    token = (body.get("token") or "").strip()
    ids = body.get("ids", [])

    if not token:
        return jsonify({"error": "No token provided"}), 400
    if not ids:
        return jsonify({"error": "No conversation IDs provided"}), 400

    results = {"deleted": [], "failed": []}

    for conv_id in ids:
        try:
            resp = http.patch(
                f"{BASE_URL}/conversation/{conv_id}",
                headers=chatgpt_headers(token),
                json={"is_visible": False},
                timeout=15,
            )
            if resp.status_code == 200:
                results["deleted"].append(conv_id)
            else:
                results["failed"].append(conv_id)
        except requests.RequestException:
            results["failed"].append(conv_id)

    return jsonify(results)


@app.route("/api/conversation/<conv_id>/preview")
def conversation_preview(conv_id):
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "No token provided"}), 400

    try:
        resp = http.get(
            f"{BASE_URL}/conversation/{conv_id}",
            headers=chatgpt_headers(token),
            timeout=20,
        )
        if resp.status_code == 401:
            return jsonify({"error": "Invalid or expired token"}), 401
        resp.raise_for_status()

        data = resp.json()
        first_msg = _extract_first_user_message(data)
        return jsonify({"preview": first_msg})

    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


def _extract_first_user_message(conv_data: dict) -> str:
    """Walk the conversation tree and return the first user message text."""
    mapping = conv_data.get("mapping", {})
    # Find the root node and walk forward
    current_id = conv_data.get("current_node")
    # Collect all nodes in order by following parent links from current node
    chain = []
    visited = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        node = mapping.get(current_id, {})
        chain.append(node)
        current_id = node.get("parent")
    chain.reverse()  # oldest first

    for node in chain:
        msg = node.get("message") or {}
        role = (msg.get("author") or {}).get("role", "")
        if role != "user":
            continue
        content = msg.get("content") or {}
        parts = content.get("parts") or []
        text = " ".join(p for p in parts if isinstance(p, str)).strip()
        if text:
            return text[:400]  # cap at 400 chars

    return "(No message content found)"


@app.route("/api/delete-all", methods=["POST"])
def delete_all():
    body = request.get_json(force=True)
    token = (body.get("token") or "").strip()

    if not token:
        return jsonify({"error": "No token provided"}), 400

    try:
        resp = http.delete(
            f"{BASE_URL}/conversations",
            headers=chatgpt_headers(token),
            timeout=30,
        )
        if resp.status_code == 200:
            return jsonify({"success": True})
        return jsonify({"error": f"API returned {resp.status_code}"}), 502
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  ChatGPT Manager running at http://localhost:{port}\n")
    app.run(debug=False, port=port)
