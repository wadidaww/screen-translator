package com.omniview.translator

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private lateinit var prefs: Prefs
    private lateinit var overlayButton: Button
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs(this)
        overlayButton = findViewById(R.id.overlayButton)
        status = findViewById(R.id.statusText)

        val sourceSpinner = findViewById<Spinner>(R.id.sourceSpinner)
        val targetSpinner = findViewById<Spinner>(R.id.targetSpinner)
        val scriptSpinner = findViewById<Spinner>(R.id.scriptSpinner)
        val scriptLabel = findViewById<View>(R.id.scriptLabel)

        bind(sourceSpinner, Languages.sources, Languages.sources.indexOfFirst { it.code == prefs.sourceLang }) {
            val auto = it.code == Prefs.AUTO
            scriptSpinner.visibility = if (auto) View.VISIBLE else View.GONE
            scriptLabel.visibility = scriptSpinner.visibility
            // Spinners report their initial selection too: only restart on a real change.
            if (prefs.sourceLang != it.code) {
                prefs.sourceLang = it.code
                settingsChanged()
            }
        }
        bind(targetSpinner, Languages.all, Languages.all.indexOfFirst { it.code == prefs.targetLang }) {
            if (prefs.targetLang != it.code) {
                prefs.targetLang = it.code
                settingsChanged()
            }
        }
        val scripts = Script.entries.toList()
        val scriptAdapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            scripts.map { it.label })
        scriptSpinner.adapter = scriptAdapter
        scriptSpinner.setSelection(scripts.indexOf(prefs.autoScript))
        scriptSpinner.onItemSelectedListener = listener { position ->
            if (prefs.autoScript != scripts[position]) {
                prefs.autoScript = scripts[position]
                settingsChanged()
            }
        }

        overlayButton.setOnClickListener {
            startActivity(
                Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))
            )
        }
        findViewById<Button>(R.id.startButton).setOnClickListener { startBubble() }
        findViewById<Button>(R.id.stopButton).setOnClickListener {
            stopService(Intent(this, TranslatorService::class.java))
            refresh()
        }
        findViewById<Button>(R.id.downloadButton).setOnClickListener { downloadModel() }
        findViewById<Button>(R.id.textButton).setOnClickListener {
            startActivity(Intent(this, TextPanelActivity::class.java))
        }

        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
        if (intent?.getBooleanExtra(EXTRA_AUTOSTART, false) == true) startBubble()
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun refresh() {
        val granted = Settings.canDrawOverlays(this)
        overlayButton.text = if (granted) "1. Display over other apps: allowed ✓" else
            "1. Allow display over other apps"
        overlayButton.isEnabled = !granted
        status.text = when {
            !granted -> "Step 1 is needed so the floating button can appear over other apps."
            TranslatorState.serviceRunning -> "The floating button is on. Tap it in any app to translate."
            else -> "Ready. Tap “Show floating button”."
        }
    }

    private fun startBubble() {
        if (!Settings.canDrawOverlays(this)) {
            status.text = "Please allow “display over other apps” first (step 1)."
            return
        }
        TranslatorService.start(this)
        status.text = "The floating button is on. Open any app and tap it to translate."
        moveTaskToBack(true)
    }

    private fun settingsChanged() {
        if (TranslatorState.serviceRunning) {
            startService(
                Intent(this, TranslatorService::class.java)
                    .setAction(TranslatorService.ACTION_SETTINGS_CHANGED)
            )
        }
    }

    private fun downloadModel() {
        val target = prefs.targetLang
        val source = prefs.sourceLang
        status.text = "Downloading ${Languages.displayName(target)}…"
        lifecycleScope.launch {
            val engine = OcrTranslator()
            try {
                engine.prepare(source, target)
                status.text = "${Languages.displayName(target)} is ready and works offline."
            } catch (e: Exception) {
                status.text = "Download failed: ${e.message}. Check your internet connection."
            } finally {
                engine.close()
            }
        }
    }

    private fun bind(
        spinner: Spinner, items: List<Language>, selected: Int, onSelect: (Language) -> Unit,
    ) {
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, items)
        spinner.setSelection(selected.coerceAtLeast(0))
        spinner.onItemSelectedListener = listener { position -> onSelect(items[position]) }
    }

    private fun listener(onSelect: (Int) -> Unit) = object : AdapterView.OnItemSelectedListener {
        override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) =
            onSelect(position)

        override fun onNothingSelected(parent: AdapterView<*>?) = Unit
    }

    companion object {
        const val EXTRA_AUTOSTART = "autostart"
    }
}
