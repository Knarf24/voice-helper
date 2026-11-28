# 🎙️ Multilingual Voice Helper

**Live demo:** https://knarf24.github.io/voice-helper/

**The problem:** many people can't easily type, read small print, or search in English. Most voice assistants only
work well in a few big languages.

**The app:** tap the microphone and **ask a question out loud in your own language** (isiZulu, isiXhosa, Afrikaans,
Sesotho, Swahili, Shona, French, Portuguese and more). The helper **answers out loud in that language**:

- **Facts:** "Who was Nelson Mandela?", "What is a black hole?" (Wikipedia)
- **Weather:** "What's the weather in Durban?" with rain chance and an umbrella tip (Open-Meteo)
- **Sums:** "What is 15 percent of 240?", "two hundred and fifty times four"
- **Time and date**
- **Translations:** "Translate good morning to Zulu", "How do you say thank you in French?"
- **Switch language by voice:** "Speak Afrikaans"

You can also type, and there are one-tap examples. The helper's brain is written in **Python** and runs **inside your
browser** with [Pyodide](https://pyodide.org); listening and speaking use the browser's built-in voice (Web Speech API).
It is hosted free on GitHub Pages and needs no API keys.

Built by combining four GeeksforGeeks Python projects:

| GeeksforGeeks project | What it does here |
|---|---|
| [Speech Recognition using Google Speech API](https://www.geeksforgeeks.org/python/speech-recognition-in-python-using-google-speech-api/) | Turns your speech into text in the language you picked (browser speech recognition; `SpeechRecognition` in `desktop.py`) |
| [Voice Search Wikipedia](https://www.geeksforgeeks.org/python/voice-search-wikipedia-using-python/) | Finds the best Wikipedia article and reads its first sentences |
| [Language Translator using Google API](https://www.geeksforgeeks.org/python/language-translator-using-google-api-in-python/) | Translates your question to English and the answer back (free MyMemory API) |
| [Text To Speech with pyttsx3](https://www.geeksforgeeks.org/python/python-text-to-speech-pyttsx-module/) | Reads the answer aloud with a voice for your language (browser voices; `pyttsx3` in `desktop.py`) |

## How it works

1. **Listen:** the browser turns speech into text, in your language.
2. **Translate in:** `helper.py` translates the words to English.
3. **Understand:** `helper.py` decides what you want (fact, weather, sum, time, translation, change language).
   Sums are parsed from words ("two hundred and fifty") and worked out with a safe calculator (no `eval`).
4. **Look it up:** Wikipedia or Open-Meteo.
5. **Translate out and speak:** the answer is translated back and read aloud. A translation is read in the target
   language's voice. If your device has no voice for a language, the answer is shown as text instead of being
   mispronounced by an English voice.

## Files

| File | What it is |
|---|---|
| `helper.py` | All the logic (Python). Network access goes through one function passed in, so it runs in the browser and on a PC |
| `web/` | The page: `index.html`, `main.js` (microphone, voices, chat log), `style.css`, and Pyodide in `web/pyodide/` |
| `desktop.py` | The same helper on your computer: `python desktop.py --lang zu` (or `--type` to type) |
| `tests/test_helper.py` | Offline tests with canned replies: `python tests/test_helper.py` |
| `build_site.sh`, `.github/workflows/pages.yml` | Builds `_site/` and publishes it to GitHub Pages |

## Browser support and privacy

Works best in **Chrome, Edge or Safari**. Firefox can't listen yet, but typing and reading aloud work.
Nothing is saved. To answer, your question is sent to the free translator, Wikipedia or Open-Meteo; in Chrome and Edge
the browser's speech recognition sends your voice to the browser maker's servers.

The free translator allows about 5,000 characters a day per visitor; English questions don't use it.

## Fast loading

The page shows straight away and Python starts in the background, so nothing waits on a
"Starting Python" screen. Anything that needs Python simply waits for it if you are quicker.

- **Saved on the device** (`web/sw.js`): after the first visit, Python (Pyodide) and its packages are kept in
  the browser, so a refresh or a later visit doesn't download them again. Every app on the same site shares
  that one saved copy. The app's own files are still fetched fresh, so updates show up right away.
- **Quick restart** (`web/pyfast.js`): the first visit also saves a snapshot of a freshly started Python.
  Later visits restore it instead of starting Python from scratch (about 1.2 s down to 0.3 s on a laptop).
  If the snapshot can't be used (for example after a Pyodide upgrade), Python starts normally and a new one
  is saved.
- `build_site.sh` writes the Pyodide version into `sw.js`, so upgrading `web/pyodide/` needs no other change.


## License

MIT. Pyodide is MPL-2.0. Facts from Wikipedia (CC BY-SA), weather from Open-Meteo (CC BY 4.0),
translations by MyMemory.
