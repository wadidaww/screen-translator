# OmniView Translator

OmniView Translator is a cross-platform desktop app for real-time screen OCR and translation overlays.

## Features
- Real-time OCR from a user-selected screen region
- Offline-first translation via Argos Translate
- Optional free online fallback using deep-translator (GoogleTranslator)
- Transparent overlay rendering for translated text
- No API keys required

## Installation
1. Install Python 3.10+.
2. Install Tesseract 5.x:
   - **Windows:** install from UB Mannheim builds and ensure `tesseract.exe` is in `PATH`.
   - **macOS:** `brew install tesseract`.
   - **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install -y tesseract-ocr`.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   python -m src.app
   ```

## Development
Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

Run formatter:
```bash
black src tests
```

Run linter:
```bash
ruff check src tests
```

Run tests:
```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

CI/CD is configured via GitHub Actions (`.github/workflows/ci-cd.yml`) to run format checks,
linter checks, tests, and package builds.

Argos language models are downloaded automatically on first use for the selected language pair.

## Screenshots
- _(Placeholder)_ Add overlay and settings screenshots here.

## Contribution
1. Fork and create a branch.
2. Keep changes focused and tested.
3. Open a PR with a clear summary.

## License
This project uses 100% free and open-source libraries. No credit card or API key is required.
