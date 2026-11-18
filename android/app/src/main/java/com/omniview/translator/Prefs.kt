package com.omniview.translator

import android.content.Context
import android.content.SharedPreferences

/** Small typed wrapper around SharedPreferences. */
class Prefs(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("omniview", Context.MODE_PRIVATE)

    var sourceLang: String
        get() = prefs.getString("source", AUTO) ?: AUTO
        set(value) = prefs.edit().putString("source", value).apply()

    var targetLang: String
        get() = prefs.getString("target", "en") ?: "en"
        set(value) = prefs.edit().putString("target", value).apply()

    /** Which ML Kit recognizer to use when the source language is "auto". */
    var autoScript: Script
        get() = Script.fromName(prefs.getString("script", Script.LATIN.name))
        set(value) = prefs.edit().putString("script", value.name).apply()

    var bubbleX: Int
        get() = prefs.getInt("bubble_x", -1)
        set(value) = prefs.edit().putInt("bubble_x", value).apply()

    var bubbleY: Int
        get() = prefs.getInt("bubble_y", 300)
        set(value) = prefs.edit().putInt("bubble_y", value).apply()

    companion object {
        const val AUTO = "auto"
    }
}
