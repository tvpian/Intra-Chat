# Contributing to Intra-Chat

Thanks for your interest in improving Intra-Chat! This is a small, opinionated
project — contributions are very welcome as long as they keep the app simple,
self-hosted, and dependency-light.

## Quick start

```bash
git clone https://github.com/tvpian/Intra-Chat.git
cd Intra-Chat
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python setup_password.py     # sets APP_PASSWORD + SECRET_KEY in .env
python app.py                # http://localhost:5656
```

## Ground rules

- **Stay local-first.** Intra-Chat runs on a LAN. Don't introduce hard
  dependencies on cloud services.
- **No new heavy ML deps.** AI features go through `ai_engine.py` and should
  remain pluggable. Ollama is the default backend.
- **Respect privacy.** Don't commit chat history, uploads, `.env`, or any
  personal data. Check `.gitignore` before pushing.
- **Keep the surface small.** Prefer fixing/polishing existing features over
  adding new ones unless there's a clear use case.

## Workflow

1. Fork the repo and create a feature branch:
   `git checkout -b feat/short-description`
2. Make focused commits. Keep unrelated changes out.
3. Run the app locally and click through the flow you touched.
4. Open a PR with a short description and (ideally) a screenshot or GIF.

## Reporting bugs

Open an issue with:

- What you expected
- What happened
- Steps to reproduce
- Browser + OS + Python version

## Areas where help is welcome

- More AI backends in `ai_engine.py` (OpenAI, llama.cpp, Hugging Face TGI)
- Optional SQLite persistence (currently JSON files)
- Tests
- Theming / dark-mode polish
- Internationalisation

## Code style

- Python: standard library + Flask idioms, no aggressive abstractions.
- HTML/JS: vanilla — no build step. Inline `<style>` is fine; just keep the
  same visual language.

## License

By contributing you agree that your code is released under the
[MIT License](LICENSE).
