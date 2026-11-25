"""Desktop version: the same helper.py, with a microphone and a voice on your own computer.

    python desktop.py            # answers in English
    python desktop.py --lang zu  # ask and hear answers in isiZulu (needs a Zulu voice for speaking)
    python desktop.py --type     # type questions instead of speaking

Optional: pip install SpeechRecognition pyttsx3 (and PyAudio for the microphone).
Without them it falls back to typing and printing, like the GeeksforGeeks originals' console mode.
"""
import argparse
import asyncio
import json
import urllib.request

import helper


async def get_json(url: str) -> dict:
    def fetch():
        req = urllib.request.Request(url, headers={"User-Agent": "voice-helper-desktop/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    return await asyncio.to_thread(fetch)


def make_listener(lang_tag: str, typed: bool):
    if not typed:
        try:
            import speech_recognition as sr  # GeeksforGeeks: Speech Recognition using Google Speech API
            rec, mic = sr.Recognizer(), sr.Microphone()

            def listen():
                with mic as source:
                    rec.adjust_for_ambient_noise(source, duration=0.4)
                    print("🎤 Listening…")
                    audio = rec.listen(source, phrase_time_limit=8)
                try:
                    return rec.recognize_google(audio, language=lang_tag)
                except sr.UnknownValueError:
                    return ""
            return listen
        except Exception as e:  # no package or no microphone
            print(f"(Microphone not available: {e}. Type your questions.)")
    return lambda: input("You: ")


def make_speaker():
    try:
        import pyttsx3  # GeeksforGeeks: Text To Speech with pyttsx3
        engine = pyttsx3.init()

        def say(part):
            for v in engine.getProperty("voices"):
                langs = " ".join(str(x) for x in (getattr(v, "languages", []) or [])) + " " + v.id
                if part["lang"] in langs.lower():
                    engine.setProperty("voice", v.id)
                    break
            engine.say(part["text"])
            engine.runAndWait()
        return say
    except Exception:
        return lambda part: None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", default="en", choices=sorted(helper.LANGUAGES))
    ap.add_argument("--type", action="store_true", help="type instead of using the microphone")
    a = ap.parse_args()
    lang = a.lang
    listen, say = make_listener(helper.LANGUAGES[lang][2], a.type), make_speaker()
    print(helper.HELP, "\nSay or type 'quit' to stop.\n")
    while True:
        try:
            q = listen().strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in ("quit", "exit", "stop", "bye"):
            break
        res = asyncio.run(helper.answer(q, lang, get_json))
        if res["set_lang"]:
            lang = res["set_lang"]
            listen = make_listener(helper.LANGUAGES[lang][2], a.type)
        for part in res["say"]:
            print("Helper:", part["text"])
            say(part)
        if res["source"]:
            print("  (source:", res["source"] + ")")


if __name__ == "__main__":
    main()
