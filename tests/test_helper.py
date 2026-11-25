"""Offline tests: the internet is replaced by canned replies. Run: python -m pytest tests  (or python tests/test_helper.py)"""
import asyncio
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import helper  # noqa: E402

DICT = {  # (source, target, text) -> translation
    ("zu", "en", "ubani uNelson Mandela?"): "who is Nelson Mandela?",
    ("en", "zu", "Nelson Mandela was a South African leader."): "UNelson Mandela wayengumholi waseNingizimu Afrika.",
    ("en", "fr", "good morning"): "bonjour",
    ("en", "zu", "Okay, I will listen and answer in Zulu."): "Kulungile, ngizolalela ngiphendule ngesiZulu.",
}


async def fake_get_json(url):
    u = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if "mymemory" in u.netloc:
        src, dst = q["langpair"].split("|")
        text = DICT.get((src, dst, q["q"]), f"[{dst}] {q['q']}")
        return {"responseData": {"translatedText": text}, "responseStatus": 200}
    if "wikipedia" in u.netloc:
        assert q["origin"] == "*"
        return {"query": {"pages": {"1": {"title": "Nelson Mandela", "fullurl": "https://en.wikipedia.org/wiki/Nelson_Mandela",
                                          "extract": "Nelson Mandela (18 July 1918 – 5 December 2013) was a South African leader."}}}}
    if "geocoding" in u.netloc:
        assert q["name"] == "durban"
        return {"results": [{"name": "Durban", "country": "South Africa", "latitude": -29.86, "longitude": 31.03}]}
    if "open-meteo" in u.netloc:
        return {"current": {"temperature_2m": 24.4, "weather_code": 61, "wind_speed_10m": 18.2},
                "daily": {"temperature_2m_max": [27.1], "temperature_2m_min": [19.6], "precipitation_probability_max": [70]}}
    raise AssertionError(url)


def ask(q, lang="en", now=None):
    return asyncio.run(helper.answer(q, lang, fake_get_json, now))


def test_parse():
    P = helper.parse
    assert P("Who is Nelson Mandela?") == ("wiki", {"topic": "nelson mandela"})
    assert P("Tell me about black holes") == ("wiki", {"topic": "black holes"})
    assert P("Translate good morning to Zulu") == ("translate", {"text": "good morning", "lang": "zu"})
    assert P("How do you say thank you in French?") == ("translate", {"text": "thank you", "lang": "fr"})
    assert P("What's the weather in Durban today?") == ("weather", {"place": "durban"})
    assert P("Will it rain in Cape Town tomorrow") == ("weather", {"place": "cape town"})
    assert P("What time is it?")[0] == "time"
    assert P("What is the date today")[0] == "date"
    assert P("speak isiZulu") == ("set_language", {"lang": "zu"})
    assert P("hello")[0] == "hello"
    assert P("what can you do")[0] == "help"


def test_math():
    E = lambda s: helper.evaluate(helper.to_expression(helper.clean(s)))  # noqa: E731
    assert E("What is 15 percent of 240?") == 36
    assert E("what is two hundred and fifty times four") == 1000
    assert E("square root of 81") == 9
    assert E("12 divided by 5") == 2.4
    assert E("3 to the power of 4") == 81
    assert E("what's 1,200 minus 350") == 850
    assert helper.to_expression("what is a black hole") is None
    assert helper.parse("what is 7 times 8")[0] == "math"
    assert helper.say_number(2.4) == "2.4" and helper.say_number(1000.0) == "1,000"


def test_unsafe_math_rejected():
    for bad in ("__import__('os')", "9 ** 9999", "open('x')"):
        try:
            helper.evaluate(bad)
        except Exception:
            continue
        raise AssertionError(bad)


def test_answer_wiki_in_zulu():
    r = ask("ubani uNelson Mandela?", "zu")
    assert r["kind"] == "wiki" and r["heard_en"] == "who is Nelson Mandela?"
    assert r["say"][0] == {"text": "UNelson Mandela wayengumholi waseNingizimu Afrika.", "lang": "zu", "tag": "zu-ZA"}
    assert r["source"].endswith("Nelson_Mandela")


def test_answer_translate():
    r = ask("translate good morning to French")
    assert r["kind"] == "translate"
    assert r["say"][1] == {"text": "bonjour", "lang": "fr", "tag": "fr-FR"}


def test_answer_weather():
    r = ask("weather in Durban")
    text = r["say"][0]["text"]
    assert "Durban, South Africa" in text and "24 degrees" in text and "light rain" in text and "umbrella" in text


def test_answer_time_math_language():
    assert ask("what time is it", now="2026-11-26T09:05:00")["say"][0]["text"] == "It is 9:05 AM."
    assert ask("what is the date", now="2026-11-26T09:05:00")["say"][0]["text"] == "Today is Thursday, 26 November 2026."
    assert ask("what is 7 times 8")["say"][0]["text"] == "7 times 8 is 56."
    r = ask("switch to Zulu")
    assert r["set_lang"] == "zu" and r["say"][0]["lang"] == "zu"


def test_errors_are_spoken():
    async def down(url):
        raise OSError("offline")
    r = asyncio.run(helper.answer("who is Mandela", "en", down))
    assert r["error"] and "internet" in r["say"][0]["text"]

    async def limit(url):
        return {"responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS"}, "responseStatus": 200}
    r = asyncio.run(helper.answer("sawubona", "zu", limit))
    assert "limit" in r["error"]


def test_chunks():
    long = ("This is a sentence. " * 60).strip()
    parts = helper._chunks(long)
    assert all(len(p.encode()) <= helper.MAX_CHUNK for p in parts) and " ".join(parts) == long


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
