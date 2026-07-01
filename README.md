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
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the app:
   ```bash
   python -m src.app
   ```

Argos language models are downloaded automatically on first use for the selected language pair.

## Screenshots
- _(Placeholder)_ Add overlay and settings screenshots here.

## Contribution
1. Fork and create a branch.
2. Keep changes focused and tested.
3. Open a PR with a clear summary.

## License
This project uses 100% free and open-source libraries. No credit card or API key is required.
