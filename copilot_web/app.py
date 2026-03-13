from flask import Flask, render_template, request, jsonify, Response
import openai
import os

app = Flask(__name__)

@app.after_request
def allow_iframe(response):
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    return response

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return openai.OpenAI(api_key=api_key)

SYSTEM_PROMPT = """You are Stelic Copilot, an expert AI assistant embedded in a Power BI construction project controls dashboard.
You specialize in Primavera P6 schedules, milestone tracking, schedule variance, critical path analysis, DCMA metrics, and project risk.
Be concise, professional, and dashboard-appropriate. Use bullet points for lists. Keep responses tight — this is a side panel, not a report.
If no schedule context is provided, answer general construction project controls questions helpfully.
Never make up data. If you don't have the data, say so and suggest what the user should upload."""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return "ok", 200

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data.get("messages", [])
    context = data.get("context", "")

    client = get_client()
    if not client:
        return jsonify({"error": "No API key configured."}), 500

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\nCONTEXT PROVIDED:\n{context}"

    full_messages = [{"role": "system", "content": system}] + messages[-10:]

    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=full_messages,
            temperature=0.3
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
