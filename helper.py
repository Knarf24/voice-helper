"""Multilingual Voice Helper: the brain of the app.

You ask a question in your own language. This module
  1. translates it to English (MyMemory, free, no key),
  2. works out what you want (a fact, a translation, the weather, a sum, the time),
  3. finds the answer (Wikipedia, Open-Meteo, or plain Python),
  4. translates the answer back to your language,
and returns the pieces to say out loud, each tagged with the language to speak it in.

It runs in the browser with Pyodide (web page) and on a normal computer (desktop.py).
All network access goes through one `get_json(url)` coroutine that the caller passes in,
so the same code works in both places and can be tested without the internet.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from datetime import datetime
from typing import Awaitable, Callable
from urllib.parse import quote, urlencode

GetJson = Callable[[str], Awaitable[dict]]

# code: (name in English, name in the language itself, speech tag for the browser)
LANGUAGES: dict[str, tuple[str, str, str]] = {
    "en": ("English", "English", "en-US"),
    "zu": ("Zulu", "isiZulu", "zu-ZA"),
    "xh": ("Xhosa", "isiXhosa", "xh-ZA"),
    "af": ("Afrikaans", "Afrikaans", "af-ZA"),
    "st": ("Sotho", "Sesotho", "st-ZA"),
    "sw": ("Swahili", "Kiswahili", "sw-KE"),
    "sn": ("Shona", "chiShona", "sn-ZW"),
    "yo": ("Yoruba", "Yorùbá", "yo-NG"),
    "fr": ("French", "Français", "fr-FR"),
    "es": ("Spanish", "Español", "es-ES"),
    "pt": ("Portuguese", "Português", "pt-PT"),
    "de": ("German", "Deutsch", "de-DE"),
    "it": ("Italian", "Italiano", "it-IT"),
    "nl": ("Dutch", "Nederlands", "nl-NL"),
    "ru": ("Russian", "Русский", "ru-RU"),
    "ar": ("Arabic", "العربية", "ar-SA"),
    "hi": ("Hindi", "हिन्दी", "hi-IN"),
    "zh": ("Chinese", "中文", "zh-CN"),
    "ja": ("Japanese", "日本語", "ja-JP"),
    "ko": ("Korean", "한국어", "ko-KR"),
    "tr": ("Turkish", "Türkçe", "tr-TR"),
}

_NAME_TO_CODE = {}
for _code, (_en, _native, _tag) in LANGUAGES.items():
    _NAME_TO_CODE[_en.lower()] = _code
    _NAME_TO_CODE[_native.lower()] = _code
_NAME_TO_CODE.update({"isizulu": "zu", "isixhosa": "xh", "sesotho": "st", "kiswahili": "sw",
                      "mandarin": "zh", "chinese mandarin": "zh", "farsi": None})
_NAME_TO_CODE = {k: v for k, v in _NAME_TO_CODE.items() if v}
_LANG_NAMES_RE = "|".join(sorted((re.escape(n) for n in _NAME_TO_CODE), key=len, reverse=True))


def language_list() -> list[dict]:
    """The languages offered in the page's menu."""
    return [{"code": c, "name": en, "native": nat, "tag": tag} for c, (en, nat, tag) in LANGUAGES.items()]


def lang_code(name: str) -> str | None:
    return _NAME_TO_CODE.get(name.strip().lower())


# ---------------------------------------------------------------- translation (MyMemory)

MYMEMORY = "https://api.mymemory.translated.net/get"
MAX_CHUNK = 450  # MyMemory takes up to 500 bytes per request


def _chunks(text: str, size: int = MAX_CHUNK) -> list[str]:
    """Split long text on sentence ends so each request stays under the size limit."""
    parts, cur = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(sentence.encode()) > size:  # one very long sentence: cut on a space
            cut = sentence[:size].rfind(" ")
            cut = cut if cut > 0 else size
            parts.append(sentence[:cut]); sentence = sentence[cut:].strip()
        if cur and len((cur + " " + sentence).encode()) > size:
            parts.append(cur); cur = sentence
        else:
            cur = (cur + " " + sentence).strip()
    if cur:
        parts.append(cur)
    return parts


async def translate(text: str, source: str, target: str, get_json: GetJson) -> str:
    """Translate text between two language codes. Returns the text unchanged if they are the same."""
    if not text or source == target:
        return text
    out = []
    for piece in _chunks(text):
        url = MYMEMORY + "?" + urlencode({"q": piece, "langpair": f"{source}|{target}"})
        data = await get_json(url)
        status = int(data.get("responseStatus") or 200)
        result = ((data.get("responseData") or {}).get("translatedText") or "").strip()
        if status != 200 or not result:
            raise HelperError("translate", data.get("responseDetails") or "no translation came back")
        if "MYMEMORY WARNING" in result.upper():
            raise HelperError("translate", "the free translator's daily limit was reached; try again tomorrow")
        out.append(_unescape(result))
    return " ".join(out)


def _unescape(s: str) -> str:
    return (s.replace("&#39;", "'").replace("&quot;", '"').replace("&amp;", "&")
             .replace("&lt;", "<").replace("&gt;", ">"))


class HelperError(Exception):
    def __init__(self, service: str, detail: str):
        super().__init__(f"{service}: {detail}")
        self.service, self.detail = service, detail


# ---------------------------------------------------------------- understanding the question

_FILLER = r"(?:please|hey|hi|ok|okay|helper|voice helper|can you|could you|would you|tell me|i want to know|i'd like to know)"


def clean(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"[¿¡\"“”]", "", t)
    t = re.sub(r"[?!.]+$", "", t).strip()
    t = re.sub(rf"^(?:{_FILLER}[ ,]+)+", "", t)
    t = re.sub(r"[ ,]+please$", "", t)
    return t.strip(" ,")


def parse(text: str) -> tuple[str, dict]:
    """Work out what an English sentence is asking for. Returns (kind, details)."""
    t = clean(text)
    if not t:
        return "empty", {}

    if re.fullmatch(r"(?:hello|hi|hey|good (?:morning|afternoon|evening)|howzit|sawubona|molo)(?: there)?", t):
        return "hello", {}
    if re.fullmatch(r"(?:thanks|thank you|thank you very much|cheers)(?: so much)?", t):
        return "thanks", {}
    if re.search(r"\b(?:what can you do|help me|how do (?:i|you) use|what do you do)\b", t) or t == "help":
        return "help", {}

    m = re.fullmatch(rf"(?:switch to|change to|speak|talk in|speak in|use|answer in) ({_LANG_NAMES_RE})(?: language| please)?", t)
    if m:
        return "set_language", {"lang": lang_code(m.group(1))}

    # translation: "translate X to/into L", "how do you say X in L", "what is X in L", "say X in L"
    for pat in (
        rf"translate (?P<x>.+?) (?:to|into|in) (?P<l>{_LANG_NAMES_RE})",
        rf"how (?:do|would) (?:you|i|we) say (?P<x>.+?) in (?P<l>{_LANG_NAMES_RE})",
        rf"(?:say|what is|what's|whats) (?P<x>.+?) in (?P<l>{_LANG_NAMES_RE})",
        rf"(?P<x>.+?) in (?P<l>{_LANG_NAMES_RE}) please",
    ):
        m = re.fullmatch(pat, t)
        if m:
            phrase = m.group("x").strip(" '\"")
            return "translate", {"text": phrase, "lang": lang_code(m.group("l"))}

    if re.search(r"\b(?:what time is it|what is the time|what's the time|whats the time|the time now|current time|time is it)\b", t):
        return "time", {}
    if re.search(r"\b(?:what(?:'s| is) (?:the |today's )?date|what day is (?:it|today)|today's date|which day is it)\b", t):
        return "date", {}

    m = re.search(r"\b(?:weather|temperature|forecast|rain|raining|sunny|hot|cold|windy)\b.*?\b(?:in|at|for) (?P<p>[a-z][\w .'-]+)$", t)
    if m:
        return "weather", {"place": _strip_tail(m.group("p"))}

    expr = to_expression(t)
    if expr is not None:
        return "math", {"expr": expr}

    m = re.fullmatch(
        r"(?:who|what|where|when) (?:is|was|are|were|'s) (?:a |an |the )?(?P<x>.+)"
        r"|(?:tell me about|tell me something about|something about|about|information about|info on|search for|search|look up|define|meaning of|what does) (?:a |an |the )?(?P<y>.+?)(?: mean)?",
        t)
    if m:
        topic = (m.group("x") or m.group("y") or "").strip()
        return "wiki", {"topic": _strip_tail(topic)}
    return "wiki", {"topic": _strip_tail(re.sub(r"^(?:who|what|where|when|why|how) (?:is|was|are|were|did|do|does) ", "", t))}


def _strip_tail(s: str) -> str:
    s = re.sub(r"\b(?:today|now|right now|tomorrow|this week|please|for me)$", "", s.strip()).strip(" ,")
    return s


# ---------------------------------------------------------------- calculator (safe, no eval)

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}

_OPS = [
    (r"\bsquare root of\b", " sqrt "), (r"\bthe square of\b", " sq "), (r"\bsquared\b", " ** 2 "), (r"\bcubed\b", " ** 3 "),
    (r"\bto the power of\b", " ** "), (r"\bto the power\b", " ** "), (r"\bpower\b", " ** "),
    (r"\bpercent of\b", " / 100 * "), (r"%\s*of\b", " / 100 * "),
    (r"\bmultiplied by\b", " * "), (r"\btimes\b", " * "), (r"\bx\b", " * "), (r"×", " * "),
    (r"\bdivided by\b", " / "), (r"\bover\b", " / "), (r"÷", " / "),
    (r"\bplus\b", " + "), (r"\band\b", " + "), (r"\badd\b", " + "),
    (r"\bminus\b", " - "), (r"\bless\b", " - "), (r"\btake away\b", " - "),
]


def _words_to_numbers(t: str) -> str:
    """'two hundred and fifty' -> '250'. Leaves anything else alone."""
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)  # 1,000 -> 1000
    tokens, out, cur, total, in_num = t.split(), [], 0, 0, False
    for i, tok in enumerate(tokens + [""]):
        w = tok.replace("-", " ")
        sub = w.split()
        if sub and all(s in _NUMBER_WORDS or s in _SCALES for s in sub):
            for s in sub:
                if s in _NUMBER_WORDS:
                    cur += _NUMBER_WORDS[s]
                elif s == "hundred":
                    cur = (cur or 1) * 100
                else:
                    total += (cur or 1) * _SCALES[s]; cur = 0
            in_num = True
            continue
        # "and" inside a number ("two hundred and five") belongs to the number
        if tok == "and" and in_num and i + 1 < len(tokens) and tokens[i + 1] in _NUMBER_WORDS:
            continue
        if in_num:
            out.append(str(total + cur)); cur = total = 0; in_num = False
        if tok:
            out.append(tok)
    return " ".join(out)


def to_expression(t: str) -> str | None:
    """Turn a spoken sum into a Python expression, or None if it is not a sum."""
    s = re.sub(r"^(?:what is|what's|whats|calculate|compute|work out|how much is|solve)\s+", "", t)
    s = re.sub(r"\s*(?:equals|equal|is equal to)\s*$", "", s)
    s = _words_to_numbers(s)
    for pat, rep in _OPS:
        s = re.sub(pat, rep, s)
    s = re.sub(r"(?<=\d)\s*%", " / 100 ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not re.search(r"\d", s) or re.search(r"[a-wyz]", s.replace("sqrt", "").replace("sq", "")):
        return None
    if not re.search(r"[-+*/]|sqrt|sq", s):
        return None
    s = re.sub(r"\bsqrt\s+([\d.]+)", r"sqrt(\1)", s)
    s = re.sub(r"\bsq\s+([\d.]+)", r"(\1 ** 2)", s)
    try:
        evaluate(s)
    except Exception:
        return None
    return s


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod}


def evaluate(expr: str) -> float:
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(b) > 100:
                raise ValueError("power too big")
            return _BIN[type(node.op)](a, b)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "sqrt" and len(node.args) == 1:
            return math.sqrt(ev(node.args[0]))
        raise ValueError("not a simple sum")
    return ev(ast.parse(expr, mode="eval"))


def say_number(v: float) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}"
    return f"{round(v, 4):,}".rstrip("0").rstrip(".")


def say_expression(expr: str) -> str:
    s = expr.replace("sqrt(", "the square root of (").replace("**", "to the power of")
    s = s.replace("*", "times").replace("/ 100 times", "percent of").replace("/", "divided by")
    s = s.replace("+", "plus").replace(" - ", " minus ")
    return re.sub(r"[()]", "", re.sub(r"\s+", " ", s)).strip()


# ---------------------------------------------------------------- weather (Open-Meteo, free, no key)

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
    82: "heavy showers", 85: "snow showers", 86: "heavy snow showers", 95: "a thunderstorm",
    96: "a thunderstorm with hail", 99: "a thunderstorm with hail",
}


async def weather(place: str, get_json: GetJson) -> tuple[str, str]:
    geo = await get_json("https://geocoding-api.open-meteo.com/v1/search?" +
                         urlencode({"name": place, "count": 1, "language": "en", "format": "json"}))
    hits = geo.get("results") or []
    if not hits:
        return f"Sorry, I couldn't find a place called {place.title()}.", ""
    p = hits[0]
    name = ", ".join(x for x in (p.get("name"), p.get("country")) if x)
    fc = await get_json("https://api.open-meteo.com/v1/forecast?" + urlencode({
        "latitude": p["latitude"], "longitude": p["longitude"], "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    }))
    cur, day = fc.get("current") or {}, fc.get("daily") or {}
    sky = WEATHER_CODES.get(int(cur.get("weather_code", -1)), "mixed weather")
    temp = round(float(cur.get("temperature_2m", 0)))
    wind = round(float(cur.get("wind_speed_10m", 0)))
    first = lambda k: (day.get(k) or [None])[0]  # noqa: E731
    hi, lo, rain = first("temperature_2m_max"), first("temperature_2m_min"), first("precipitation_probability_max")
    text = f"In {name} it is {temp} degrees with {sky} and wind at {wind} kilometres an hour."
    if hi is not None and lo is not None:
        text += f" Today: high {round(hi)}, low {round(lo)} degrees."
    if rain is not None:
        text += f" Chance of rain: {round(rain)} percent."
        if rain >= 50:
            text += " Take an umbrella."
    src = f"https://open-meteo.com/en/docs#latitude={p['latitude']}&longitude={p['longitude']}"
    return text, src


# ---------------------------------------------------------------- facts (Wikipedia, free, no key)

async def wikipedia(topic: str, get_json: GetJson, sentences: int = 3) -> tuple[str, str]:
    if not topic:
        return "What would you like to know about?", ""
    url = "https://en.wikipedia.org/w/api.php?" + urlencode({
        "action": "query", "format": "json", "origin": "*", "redirects": 1,
        "generator": "search", "gsrsearch": topic, "gsrlimit": 1,
        "prop": "extracts|info", "exintro": 1, "explaintext": 1, "exsentences": sentences, "inprop": "url",
    })
    data = await get_json(url)
    pages = list(((data.get("query") or {}).get("pages") or {}).values())
    if not pages:
        return f"Sorry, I couldn't find anything about {topic}.", ""
    page = pages[0]
    extract = re.sub(r"\s*\([^()]*\)", "", page.get("extract") or "")  # drop pronunciations and dates in brackets
    extract = re.sub(r"\s+", " ", extract).strip()
    if not extract:
        return f"I found the article {page.get('title')}, but it has no summary.", page.get("fullurl", "")
    if " may refer to" in extract[:200]:
        return f"{topic.title()} can mean several things. Try asking more precisely.", page.get("fullurl", "")
    src = page.get("fullurl") or "https://en.wikipedia.org/wiki/" + quote(page.get("title", "").replace(" ", "_"))
    return extract, src


# ---------------------------------------------------------------- the whole flow

HELP = ("You can ask me who or what something is, the weather in a city, a sum such as 15 percent of 240, "
        "the time or date, or to translate a phrase, for example: translate good morning to Zulu.")


def _speech(text: str, lang: str) -> dict:
    return {"text": text, "lang": lang, "tag": LANGUAGES.get(lang, LANGUAGES["en"])[2]}


async def answer(question: str, lang: str, get_json: GetJson, now_iso: str | None = None) -> dict:
    """Answer one question asked in language `lang`.

    Returns {"kind", "heard_en", "say": [{"text","lang","tag"}...], "source", "set_lang", "error"}.
    """
    lang = lang if lang in LANGUAGES else "en"
    result = {"kind": "", "heard_en": question, "say": [], "source": "", "set_lang": "", "error": ""}
    try:
        english = await translate(question, lang, "en", get_json) if lang != "en" else question
        result["heard_en"] = english
        kind, info = parse(english)
        if kind == "wiki" and lang != "en" and not info.get("topic"):
            kind, info = parse(question)  # untranslated names, e.g. a place
        result["kind"] = kind
        reply, src, extra = "", "", []

        if kind == "empty":
            reply = "I didn't catch that. Please try again."
        elif kind == "hello":
            reply = "Hello! Ask me anything. " + HELP
        elif kind == "thanks":
            reply = "You're welcome!"
        elif kind == "help":
            reply = HELP
        elif kind == "set_language":
            new = info["lang"]
            result["set_lang"] = new
            msg = f"Okay, I will listen and answer in {LANGUAGES[new][0]}."
            result["say"] = [_speech(await translate(msg, "en", new, get_json), new)]
            return result
        elif kind == "time" or kind == "date":
            now = datetime.fromisoformat(now_iso) if now_iso else datetime.now()
            if kind == "time":
                reply = "It is " + now.strftime("%I:%M %p").lstrip("0") + "."
            else:
                reply = "Today is " + now.strftime("%A, %d %B %Y").replace(" 0", " ") + "."
        elif kind == "math":
            value = evaluate(info["expr"])
            reply = f"{say_expression(info['expr'])} is {say_number(value)}."
        elif kind == "weather":
            reply, src = await weather(info["place"], get_json)
        elif kind == "translate":
            target = info["lang"]
            # Translate the phrase as the user said it (their language) when we can find it, else the English.
            said = await translate(info["text"], "en", target, get_json)
            reply = f'"{info["text"]}" in {LANGUAGES[target][0]} is:'
            extra = [_speech(said, target)]
        else:
            reply, src = await wikipedia(info.get("topic", ""), get_json)

        reply_local = await translate(reply, "en", lang, get_json) if lang != "en" else reply
        result["say"] = [_speech(reply_local, lang)] + extra
        result["source"] = src
    except HelperError as e:
        result["error"] = e.detail
        result["say"] = [_speech(f"Sorry, the {e.service} service had a problem: {e.detail}", "en")]
    except Exception as e:  # network down, bad reply...
        result["error"] = str(e) or type(e).__name__
        result["say"] = [_speech("Sorry, I couldn't reach the internet to answer that. Please try again.", "en")]
    return result


# ---------------------------------------------------------------- Pyodide entry point

async def answer_json(question: str, lang: str, now_iso: str = "") -> str:
    """Called from the web page. Uses the browser's fetch through Pyodide."""
    import json
    from pyodide.http import pyfetch  # type: ignore

    async def get_json(url: str) -> dict:
        resp = await pyfetch(url)
        if not resp.ok:
            raise RuntimeError(f"{resp.status} from {url.split('/')[2]}")
        return await resp.json()

    return json.dumps(await answer(question, lang, get_json, now_iso or None))


def languages_json() -> str:
    import json
    return json.dumps(language_list())
