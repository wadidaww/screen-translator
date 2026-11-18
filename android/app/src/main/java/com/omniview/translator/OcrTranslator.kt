package com.omniview.translator

import android.graphics.Bitmap
import android.graphics.Rect
import android.util.Log
import android.util.LruCache
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.nl.languageid.LanguageIdentification
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.Translator
import com.google.mlkit.nl.translate.TranslatorOptions
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import com.google.mlkit.vision.text.devanagari.DevanagariTextRecognizerOptions
import com.google.mlkit.vision.text.japanese.JapaneseTextRecognizerOptions
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.tasks.await

/** A paragraph of on-screen text, where it is, and what it becomes. */
data class TextItem(
    val text: String,
    val box: Rect,
    var translated: String = "",
    var background: Int = 0,
    var foreground: Int = 0,
)

/** ML Kit OCR + language ID + on-device translation, with caches. */
class OcrTranslator {
    private val recognizers = HashMap<Script, TextRecognizer>()
    private val translators = HashMap<Pair<String, String>, Translator>()
    private val readyModels = HashSet<Pair<String, String>>()
    private val languageId = LanguageIdentification.getClient()
    private val cache = LruCache<String, String>(2000)

    /** Called when a translation model starts downloading (first use of a language). */
    var onDownloading: (Boolean) -> Unit = {}

    private fun recognizer(script: Script): TextRecognizer = recognizers.getOrPut(script) {
        when (script) {
            Script.LATIN -> TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
            Script.CHINESE ->
                TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build())
            Script.JAPANESE ->
                TextRecognition.getClient(JapaneseTextRecognizerOptions.Builder().build())
            Script.KOREAN ->
                TextRecognition.getClient(KoreanTextRecognizerOptions.Builder().build())
            Script.DEVANAGARI ->
                TextRecognition.getClient(DevanagariTextRecognizerOptions.Builder().build())
        }
    }

    suspend fun recognize(frame: Bitmap, script: Script): List<TextItem> {
        val result = recognizer(script).process(InputImage.fromBitmap(frame, 0)).await()
        val cjk = script == Script.CHINESE || script == Script.JAPANESE
        return result.textBlocks.mapNotNull { block ->
            val box = block.boundingBox ?: return@mapNotNull null
            val text = block.lines.joinToString(if (cjk) "" else " ") { it.text }.trim()
            if (isNoise(text)) null else TextItem(text, box)
        }
    }

    private fun isNoise(text: String): Boolean {
        if (text.isBlank()) return true
        val letters = text.count { it.isLetter() }
        if (letters == 0) return true
        return text.length < 2 && !Character.isIdeographic(text.codePointAt(0))
    }

    private suspend fun detect(text: String): String? = try {
        val code = languageId.identifyLanguage(text).await()
        if (code == "und") null else code.substringBefore('-')
    } catch (e: Exception) {
        null
    }

    private suspend fun translator(source: String, target: String): Translator? {
        val src = TranslateLanguage.fromLanguageTag(source) ?: return null
        val tgt = TranslateLanguage.fromLanguageTag(target) ?: return null
        val key = src to tgt
        val translator = translators.getOrPut(key) {
            Translation.getClient(
                TranslatorOptions.Builder().setSourceLanguage(src).setTargetLanguage(tgt).build()
            )
        }
        if (key !in readyModels) {
            onDownloading(true)
            try {
                translator.downloadModelIfNeeded(DownloadConditions.Builder().build()).await()
                readyModels.add(key)
            } finally {
                onDownloading(false)
            }
        }
        return translator
    }

    /** Downloads the model for a language pair ahead of time (used by the settings screen). */
    suspend fun prepare(source: String, target: String) {
        val src = if (source == Prefs.AUTO) TranslateLanguage.ENGLISH else source
        if (src != target) translator(src, target)
    }

    /** Translates items in place and returns the ones that actually changed. */
    suspend fun translate(items: List<TextItem>, source: String, target: String): List<TextItem> {
        val out = ArrayList<TextItem>()
        for (item in items) {
            val lang = if (source == Prefs.AUTO) detect(item.text) ?: "en" else source
            if (lang == target) continue
            val key = "$lang|$target|${item.text}"
            val cached = cache.get(key)
            val translated = cached ?: try {
                val t = translator(lang, target) ?: continue
                t.translate(item.text).await().also { cache.put(key, it) }
            } catch (e: Exception) {
                Log.w(TAG, "Translation failed for $lang -> $target", e)
                continue
            }
            if (translated.isNotBlank() && !translated.equals(item.text, ignoreCase = true)) {
                item.translated = translated
                out.add(item)
            }
        }
        return out
    }

    fun close() {
        recognizers.values.forEach { it.close() }
        translators.values.forEach { it.close() }
        languageId.close()
    }

    companion object {
        private const val TAG = "OcrTranslator"
    }
}
