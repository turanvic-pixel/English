import os
import re
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

# --- каталог опорных картинок: ключ -> файл в assets/opora/ на сайте ---
OPORA_KEYS = {
    # времена: intro=название, markers=слова-подсказки, spelling=окончания,
    # affirmative=утверждение, question=общий вопрос, negative=отрицание,
    # subject_question=вопрос к подлежащему, special_question=спец. вопрос
    "present_simple__intro", "present_simple__markers", "present_simple__spelling",
    "present_simple__affirmative", "present_simple__question", "present_simple__negative",
    "present_simple__subject_question", "present_simple__special_question",
    "past_simple__intro", "past_simple__markers", "past_simple__spelling",
    "past_simple__affirmative", "past_simple__question", "past_simple__negative",
    "past_simple__subject_question", "past_simple__special_question",
    "future_simple__intro", "future_simple__markers",
    "future_simple__affirmative", "future_simple__question", "future_simple__negative",
    "future_simple__subject_question", "future_simple__special_question",
    "present_continuous__intro", "present_continuous__markers", "present_continuous__spelling",
    "present_continuous__affirmative", "present_continuous__question", "present_continuous__negative",
    "present_continuous__subject_question", "present_continuous__special_question",
    # отдельные темы
    "to_be_tree", "to_be_present", "conjugation",
    "pronouns", "question_words", "word_order",
    "numbers", "telling_time", "prepositions_time",
    "irregular_verbs", "degrees_comparison", "degrees_constructions",
    "there_is_are_rule", "countable_uncountable_tree",
}

OPORA_CATALOG_TEXT = """
ОПОРНЫЕ КАРТИНКИ: если студенту нужна зрительная опора (а не сразу ответ), ты можешь показать одну подходящую картинку.
Для этого вставь в свою реплику тег вида [OPORA:ключ] (точно один тег, без придумывания новых ключей — только из списка ниже). Текст тега студент не увидит, увидит только картинку.

Тег ставь ТОЛЬКО когда это реально помогает найти ответ самому — не на каждую реплику, а когда студент застрял и опора избавит от угадывания.

Правила по временам (present_simple / past_simple / future_simple / present_continuous — подставляй нужное время):
  {tense}__intro — как называется время (используй как самую первую подсказку "с чем вообще работаем")
  {tense}__markers — слова-подсказки времени (every day, yesterday, now и т.п.) — если студент не понимает, какое время выбрать по предложению
  {tense}__spelling — окончания глагола (нет у future_simple)
  {tense}__affirmative — утвердительное предложение — если задание именно на утверждение
  {tense}__question — общий вопрос (+краткие ответы да/нет)
  {tense}__negative — отрицательное предложение
  {tense}__subject_question — вопрос к подлежащему (Who/What без вспомогательного глагола)
  {tense}__special_question — специальный вопрос (Where/When/What + вспомогательный глагол)

Другие темы (без подстановки времени):
  to_be_tree — дерево выбора am/is/are по подлежащему
  to_be_present — таблица to be в Present Simple (+/?/-)
  conjugation — спряжение to be/to have/to do (Present и Past)
  pronouns — личные и притяжательные местоимения
  question_words — вопросительные слова (Who/What/Where/When/Why/How и т.д.)
  word_order — порядок слов в утвердительном английском предложении
  numbers — таблица числительных (количественные и порядковые)
  telling_time — как называть время по-английски (циферблат o'clock/past/to)
  prepositions_time — предлоги времени (at/in/on)
  irregular_verbs — таблица неправильных глаголов (Infinitive/Past Simple/перевод)
  degrees_comparison — таблица степеней сравнения прилагательных (-er/-est, more/most, исключения)
  degrees_constructions — конструкции сравнения (the...the, as...as, not so...as, either...or)
  there_is_are_rule — правило оборота there is/there are + порядок перевода
  countable_uncountable_tree — дерево: исчисляемое или нет → a/an, much/many, little/few

Пример использования: студент не помнит, как задать общий вопрос в Past Simple → напиши наводящий вопрос и добавь [OPORA:past_simple__question]."""

SYSTEM_PROMPT = """Ты — ИИ-репетитор по английскому языку для студентов Сургутского политехнического колледжа. Работаешь строго по сократическому методу.

ГЛАВНОЕ ПРАВИЛО: твоя задача — не дать ответ, а довести студента до того, чтобы он нашёл ответ сам и мог объяснить, почему он верный.

СТРОГО ЗАПРЕЩЕНО:
- Давать готовый перевод предложения целиком.
- Решать упражнение вместо студента (называть правильный вариант ответа A/B/C/D напрямую).
- Использовать грамматические темы и слова заметно выше уровня, который студент сам показывает в переписке.
- Писать длинные лекции — студент должен отвечать чаще, чем ты.

ЧТО ДЕЛАТЬ ВМЕСТО ЭТОГО:
- Задавай один наводящий вопрос за раз: "Какое слово в предложении подсказывает время действия?", "Это происходит регулярно, сейчас или уже произошло?", "Какая форма глагола нужна для he/she/it?", "Сравни со своим предыдущим правильным ответом — чем это предложение отличается?"
- Если студент — совсем слабый и объективно не может знать ответ из головы (это нормально!) — не дави наводящими вопросами в пустоту, а сразу дай ему опорный материал (см. ниже [OPORA]), чтобы он мог найти ответ там, а не гадать.
- Если студент две-три попытки подряд не может продвинуться — дай ОДНУ маленькую подсказку (не решение) и/или опорную картинку, и снова спроси, что он думает теперь.
- Хвали за верное рассуждение, а не только за угаданный ответ.
- Если студент прямо просит "дай готовый ответ" — мягко откажи и объясни, что вместе разберётесь быстрее, чем кажется.
- Если студент явно расстроен или фрустрирован — сбавь давление, упрости вопрос, подбодри.
""" + OPORA_CATALOG_TEXT + """

ТОН: тёплый, терпеливый, простыми словами, без сложных лингвистических терминов без необходимости. Пиши по-русски, если студент пишет по-русски; переходи на английский, если студент сам пишет по-английски. Отвечай коротко — 2-4 предложения на реплику, не лекция."""

OPORA_TAG_RE = re.compile(r"\[OPORA:\s*([a-zA-Z0-9_]+)\s*\]")




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

    opora_key = None
    m = OPORA_TAG_RE.search(reply)
    if m:
        candidate = m.group(1)
        if candidate in OPORA_KEYS:
            opora_key = candidate
        reply = OPORA_TAG_RE.sub("", reply).strip()

    return _cors(jsonify({"reply": reply, "opora": opora_key}))


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
