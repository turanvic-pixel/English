import os
import json
import time
from collections import deque

from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# --- секрет только из окружения, без запасного значения по умолчанию ---
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://turanvic-pixel.github.io")

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

SYSTEM_PROMPT = """Ты — ИИ-репетитор по английскому языку для студентов Сургутского политехнического колледжа. Работаешь строго по сократическому методу.

ГЛАВНОЕ ПРАВИЛО: твоя задача — не дать ответ, а довести студента до того, чтобы он нашёл ответ сам и мог объяснить, почему он верный.

СТРОГО ЗАПРЕЩЕНО:
- Давать готовый перевод предложения целиком.
- Решать упражнение вместо студента (называть правильный вариант ответа A/B/C/D напрямую).
- Использовать грамматические темы и слова заметно выше уровня, который студент сам показывает в переписке.
- Писать длинные лекции — студент должен отвечать чаще, чем ты.

ЧТО ДЕЛАТЬ ВМЕСТО ЭТОГО:
- Задавай один наводящий вопрос за раз: "Какое слово в предложении подсказывает время действия?", "Это происходит регулярно, сейчас или уже произошло?", "Какая форма глагола нужна для he/she/it?", "Сравни со своим предыдущим правильным ответом — чем это предложение отличается?"
- Если студент две-три попытки подряд не может продвинуться — дай ОДНУ маленькую подсказку (не решение), и снова спроси, что он думает теперь.
- Хвали за верное рассуждение, а не только за угаданный ответ.
- Если студент прямо просит "дай готовый ответ" — мягко откажи и объясни, что вместе разберётесь быстрее, чем кажется, задав ему следующий наводящий вопрос.
- Если студент явно расстроен или фрустрирован — сбавь давление, упрости вопрос, подбодри.

ТОН: тёплый, терпеливый, простыми словами, без сложных лингвистических терминов без необходимости. Пиши по-русски, если студент пишет по-русски; переходи на английский, если студент сам пишет по-английски. Отвечай коротко — 2-4 предложения на реплику, не лекция."""


# --- очень простая защита от перегрузки бесплатного лимита Gemini (10 запросов/мин) ---
# храним временные метки последних запросов и мягко ждём, если частота слишком высокая
_recent_requests = deque()
_RATE_LIMIT = 9  # чуть меньше реального лимита Gemini для запаса
_RATE_WINDOW = 60  # секунд


def _throttle():
    now = time.time()
    while _recent_requests and now - _recent_requests[0] > _RATE_WINDOW:
        _recent_requests.popleft()
    if len(_recent_requests) >= _RATE_LIMIT:
        wait = _RATE_WINDOW - (now - _recent_requests[0]) + 0.1
        if wait > 0:
            time.sleep(min(wait, 15))  # не ждём вечно одним запросом
    _recent_requests.append(time.time())


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "english-ai-tutor"})


@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return _cors(jsonify({}))

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []  # [{role: 'user'|'model', text: '...'}, ...]
    student_context = (data.get("studentContext") or "").strip()

    if not message:
        return _cors(jsonify({"error": "empty message"})), 400
    if len(message) > 2000:
        return _cors(jsonify({"error": "message too long"})), 400

    contents = []
    for turn in history[-20:]:  # ограничиваем историю, чтобы не раздувать токены
        role = "user" if turn.get("role") == "user" else "model"
        text = str(turn.get("text", ""))[:2000]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    system_text = SYSTEM_PROMPT
    if student_context:
        system_text += "\n\nКОНТЕКСТ О СТУДЕНТЕ:\n" + student_context[:1000]

    payload = {
        "system_instruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 400},
    }

    try:
        _throttle()
        resp = requests.post(
            GEMINI_URL,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30,
        )
    except requests.RequestException as e:
        return _cors(jsonify({"error": "network error", "detail": str(e)})), 502

    if resp.status_code != 200:
        return _cors(jsonify({"error": "gemini error", "status": resp.status_code, "detail": resp.text[:500]})), 502

    try:
        body = resp.json()
        reply = body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError):
        reply = "Извини, не получилось сформулировать ответ. Попробуй переформулировать вопрос."

    return _cors(jsonify({"reply": reply}))


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
