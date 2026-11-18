package com.omniview.translator

import com.google.mlkit.nl.translate.TranslateLanguage
import java.util.Locale

/** ML Kit OCR recognizers ("scripts"). Each one also reads Latin letters. */
enum class Script(val label: String) {
    LATIN("Latin (English, Indonesian, Spanish…)"),
    CHINESE("Chinese"),
    JAPANESE("Japanese"),
    KOREAN("Korean"),
    DEVANAGARI("Devanagari (Hindi, Marathi…)");

    companion object {
        fun fromName(name: String?): Script = entries.firstOrNull { it.name == name } ?: LATIN

        fun forLanguage(code: String): Script? = when (code) {
            "zh" -> CHINESE
            "ja" -> JAPANESE
            "ko" -> KOREAN
            "hi", "mr" -> DEVANAGARI
            Prefs.AUTO -> null
            else -> LATIN
        }
    }
}

data class Language(val code: String, val name: String) {
    override fun toString() = name
}

object Languages {
    /** Every language ML Kit can translate, sorted by name. */
    val all: List<Language> by lazy {
        TranslateLanguage.getAllLanguages()
            .map { code -> Language(code, displayName(code)) }
            .sortedBy { it.name }
    }

    val sources: List<Language> by lazy { listOf(Language(Prefs.AUTO, "Auto detect")) + all }

    fun displayName(code: String): String {
        val locale = Locale.forLanguageTag(code)
        val name = locale.getDisplayName(Locale.getDefault())
        return if (name.isBlank() || name == code) code else "$name ($code)"
    }
}
