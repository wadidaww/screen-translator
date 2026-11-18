package com.omniview.translator

import android.content.ClipData
import android.content.ClipboardManager
import android.graphics.Typeface
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

/**
 * Lists the last translated text (original + translation) so it can be read comfortably
 * and copied. Tap an entry to copy its translation, long-press to copy the original.
 */
class TextPanelActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "Translated text"
        val density = resources.displayMetrics.density
        val pad = (16 * density).toInt()
        val items = TranslatorState.lastItems

        val list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad / 2, pad, pad / 2)
        }
        if (items.isEmpty()) {
            list.addView(TextView(this).apply {
                text = "Nothing translated yet. Tap the floating button in any app first."
                textSize = 15f
                setPadding(0, pad, 0, pad)
            })
        }
        for (item in items) {
            list.addView(entry(item, pad))
        }

        val copyAll = Button(this).apply {
            text = "Copy all translations"
            isEnabled = items.isNotEmpty()
            setOnClickListener {
                copy(items.joinToString("\n\n") { it.translated }, "All translations copied")
            }
        }
        val copyBoth = Button(this).apply {
            text = "Copy original + translation"
            isEnabled = items.isNotEmpty()
            setOnClickListener {
                copy(
                    items.joinToString("\n\n") { "${it.text}\n→ ${it.translated}" },
                    "Copied",
                )
            }
        }
        val buttons = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, 0, pad, pad)
            addView(copyAll)
            addView(copyBoth)
        }

        val scroll = ScrollView(this).apply { addView(list) }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(buttons)
        }
        setContentView(root)
    }

    private fun entry(item: TextItem, pad: Int): View {
        val original = TextView(this).apply {
            text = item.text
            textSize = 13f
            alpha = 0.7f
            setTextIsSelectable(false)
        }
        val translated = TextView(this).apply {
            text = item.translated
            textSize = 17f
            setTypeface(typeface, Typeface.BOLD)
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, pad / 2, 0, pad / 2)
            addView(original)
            addView(translated)
            isClickable = true
            setBackgroundResource(android.R.drawable.list_selector_background)
            setOnClickListener { copy(item.translated, "Translation copied") }
            setOnLongClickListener {
                copy(item.text, "Original copied")
                true
            }
        }
    }

    private fun copy(text: String, message: String) {
        val clipboard = getSystemService(ClipboardManager::class.java)
        clipboard.setPrimaryClip(ClipData.newPlainText("Translation", text))
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }
}
