# OmniView Translator

Translate any text on your screen and see the translation painted **right on top of the original
text**, like a live "Google Lens" for your desktop and Android phone.

- **Desktop** (Windows, macOS, Linux): Python + PyQt6, Tesseract OCR, Argos (offline) or Google (free) translation.
- **Android** (8.0+): native app with a floating button. Tap it to turn translation on or off.
  On-device OCR and translation with Google ML Kit, so it works offline after the first download.

No API keys or accounts are needed.

---

## Android

### Install
1. Download the APK on your phone from the
   [`android-latest` release](../../releases/tag/android-latest)
   (or from the **Android APK** workflow run artifacts on a pull request).
2. Open it and allow "install unknown apps" for your browser/file manager when asked.

> Every CI build is signed with a fresh debug key. If an update refuses to install, uninstall the
> old version first.

### Use
1. Open **OmniView Translator**, pick *Translate from* and *Translate to*.
2. Tap **1. Allow display over other apps** and enable it.
3. Tap **2. Show floating button**. A round bubble appears over other apps.
4. Go to any app and **tap the bubble** to start translating. The first time, Android asks to
   record/cast your screen: choose **Entire screen** and **Start**.
5. **Tap the bubble again** to stop. It turns blue while active, grey when off.

Long-press the bubble for the **smart menu**: live translate on/off, translate once, swap languages,
change the target language, close the bubble. You can also add the **Screen translate** tile to
Quick Settings, or use the buttons in the notification.

Tips:
- For Japanese, Chinese, Korean or Hindi, set *Translate from* to that language (or keep *Auto detect*
  and pick the matching writing system) so the right OCR model is used.
- Translations are slightly see-through on purpose: Android only lets taps pass through overlays
  that are at most 80% opaque, so you can still tap buttons under a translation.
- "Download language now" fetches the translation model (~30 MB per language) over Wi-Fi ahead of time.

### Build it yourself
Open `android/` in Android Studio, or run `./gradlew assembleRelease` inside `android/`
(JDK 17 and the Android SDK required).

---

## Desktop

### Install
1. Install Python 3.10+.
2. Install Tesseract 5:
   - **Windows:** the [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki). It is
     found automatically in `C:\Program Files\Tesseract-OCR`; otherwise set its path in Settings.
     Tick the extra languages you need (e.g. Japanese) in the installer.
   - **macOS:** `brew install tesseract tesseract-lang`
   - **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr tesseract-ocr-jpn libxcb-cursor0`
     (add `tesseract-ocr-<lang>` for each language you read).
3. `pip install -r requirements.txt`
4. Run: `python -m src.app`

### Use
- A tray icon and a round **floating button** appear. **Click the floating button** (or the tray
  icon) to start/stop live translation of the whole screen. Right-click it for the menu.
- **Select area…** limits translation to part of the screen (faster, recommended for games/videos).
- **Translate once** translates the current screen and clears when the screen changes.
- Hotkeys (configurable in Settings): `Ctrl+Shift+T` start/stop, `Ctrl+Shift+O` translate once,
  `Ctrl+Shift+R` select area. Global hotkeys need `pynput` and do not work on Wayland.
- **Settings**: languages, translator (offline first with online fallback / offline only / online only),
  font size, opacity, refresh speed.

Translators:
- **Offline (Argos):** models download automatically the first time a language pair is used.
- **Online (Google, free):** best quality, no setup, sends the recognised text to Google.

How it avoids reading its own overlay: on Windows 10 2004+ and macOS (with
`pyobjc-framework-Cocoa`) the overlay is hidden from screenshots. On Linux it ignores the pixels under
its own boxes and briefly hides them every few seconds to check whether the text underneath changed.

Settings and logs are stored in `%APPDATA%\OmniViewTranslator` (Windows),
`~/Library/Application Support/OmniViewTranslator` (macOS) or `~/.config/OmniViewTranslator` (Linux).

### Development
```bash
pip install -r requirements-dev.txt
black src tests
ruff check src tests
python -m unittest discover -s tests -p 'test_*.py' -v
```

CI (`.github/workflows/`) runs formatting, lint and tests for Python, and builds the Android APK.

## License
This project uses only free and open-source libraries (plus Google ML Kit on Android, free to use).
No credit card or API key is required.
