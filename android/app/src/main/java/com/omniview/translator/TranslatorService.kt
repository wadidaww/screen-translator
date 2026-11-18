package com.omniview.translator

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.graphics.Rect
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.provider.Settings
import android.service.quicksettings.TileService
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Toast
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Observable on/off state shared with the Quick Settings tile and the settings screen. */
object TranslatorState {
    @Volatile
    var serviceRunning = false

    @Volatile
    var active = false

    /** What was last painted on screen, for the "Show text" panel. */
    @Volatile
    var lastItems: List<TextItem> = emptyList()
}

/**
 * Foreground service that owns the floating bubble, the screen mirror and the overlay.
 *
 * Loop (mirrors the desktop app): watch the screen; when it changes and then settles, hide the
 * old translations, OCR a clean frame, translate, and paint the results over the original text.
 * Our own overlay and bubble are masked out of change detection, and every few seconds the
 * overlay is hidden for one frame to catch text that changed underneath it.
 */
class TranslatorService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var windowManager: WindowManager
    private lateinit var prefs: Prefs
    private lateinit var bubble: FloatingBubble
    private lateinit var menu: SmartMenu
    private lateinit var overlay: TranslationOverlayView
    private lateinit var areaSelector: AreaSelector
    private val engine = OcrTranslator()

    private var projection: MediaProjection? = null
    private var capturer: ScreenCapturer? = null
    private var loopJob: Job? = null
    private var overlayAttached = false
    private var liveMode = true
    private var pendingStartLive: Boolean? = null
    private var pendingArea: Rect? = null

    /** When set, only this part of the screen (screen pixels) is read and watched. */
    private var area: Rect? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        prefs = Prefs(this)
        overlay = TranslationOverlayView(this)
        menu = SmartMenu(this, windowManager)
        areaSelector = AreaSelector(this, windowManager)
        bubble = FloatingBubble(this, windowManager, prefs, ::toggle, ::openMenu)
        engine.onDownloading = { downloading ->
            scope.launch {
                if (downloading) toast("Downloading language model… (first time only)")
            }
        }
        createChannel()
        startInForeground(withProjection = false)
        TranslatorState.serviceRunning = true
        refreshTile()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Every startForegroundService() call must be answered with startForeground().
        startInForeground(withProjection = projection != null)
        if (!Settings.canDrawOverlays(this)) {
            toast("Allow \"display over other apps\" first")
            stopSelf()
            return START_NOT_STICKY
        }
        bubble.show()
        when (intent?.action) {
            ACTION_TOGGLE -> toggle()
            ACTION_TRANSLATE_ONCE -> activate(live = false)
            ACTION_TRANSLATE_AREA -> pickArea()
            ACTION_STOP -> stopSelf()
            ACTION_PROJECTION_RESULT -> onProjectionResult(intent)
            ACTION_SETTINGS_CHANGED -> if (TranslatorState.active) restartLoop()
        }
        return START_NOT_STICKY
    }

    // ------------------------------------------------------------------ on / off
    private fun toggle() {
        if (TranslatorState.active) deactivate() else activate(live = true)
    }

    private fun activate(live: Boolean, area: Rect? = null) {
        menu.dismiss()
        if (projection == null) {
            pendingStartLive = live
            pendingArea = area
            val intent = Intent(this, ProjectionPermissionActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            return
        }
        liveMode = live
        this.area = area
        TranslatorState.active = true
        bubble.setActive(true)
        attachOverlay()
        restartLoop()
        updateNotification()
        refreshTile()
    }

    private fun deactivate() {
        menu.dismiss()
        loopJob?.cancel()
        loopJob = null
        TranslatorState.active = false
        area = null
        overlay.clear()
        bubble.setActive(false)
        bubble.setBusy(false)
        updateNotification()
        refreshTile()
    }

    private fun onProjectionResult(intent: Intent) {
        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
        val data: Intent? = if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra(EXTRA_RESULT_DATA)
        }
        val live = pendingStartLive ?: true
        val requestedArea = pendingArea
        pendingStartLive = null
        pendingArea = null
        if (resultCode == 0 || data == null) {
            toast("Screen capture permission is needed to translate")
            return
        }
        // Android 14+: the service must be a mediaProjection foreground service *before*
        // getMediaProjection() is called.
        startInForeground(withProjection = true)
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val mp = try {
            manager.getMediaProjection(resultCode, data)
        } catch (e: Exception) {
            Log.e(TAG, "getMediaProjection failed", e)
            null
        } ?: run {
            toast("Could not start screen capture")
            return
        }
        mp.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                scope.launch { onProjectionStopped() }
            }
        }, null)
        projection = mp
        val (w, h) = screenSize()
        capturer = ScreenCapturer(mp, w, h, resources.displayMetrics.densityDpi).also { it.start() }
        activate(live, requestedArea)
    }

    /** Lets the user drag a box over the screen, then translates just that part once. */
    private fun pickArea() {
        menu.dismiss()
        deactivate()
        areaSelector.show { rect ->
            if (rect != null) {
                // Give the dimmed selection layer a moment to disappear from the mirror.
                scope.launch {
                    delay(300)
                    activate(live = false, area = rect)
                }
            }
        }
    }

    private fun showTextPanel() {
        menu.dismiss()
        // The panel covers the screen, so stop watching it (the last results are kept).
        if (TranslatorState.active) deactivate()
        startActivity(
            Intent(this, TextPanelActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }

    private fun onProjectionStopped() {
        deactivate()
        capturer?.release()
        capturer = null
        projection = null
        startInForeground(withProjection = false)
    }

    private fun restartLoop() {
        loopJob?.cancel()
        overlay.clear()
        loopJob = scope.launch { runLoop() }
    }

    // ---------------------------------------------------------------- main loop
    private suspend fun runLoop() {
        val cap = capturer ?: return
        val source = prefs.sourceLang
        val target = prefs.targetLang
        val script = Script.forLanguage(source) ?: prefs.autoScript

        var shown: List<TextItem> = emptyList()
        var baseline: Signature? = null // frame as seen with our overlay, overlay masked out
        var clean: Signature? = null // the frame we translated, nothing masked
        var previous: Signature? = null
        var unstableSince = 0L
        var lastPeek = 0L
        var translatedOnce = false

        while (scope.isActive && TranslatorState.active) {
            if (menu.isShowing || areaSelector.isShowing) {
                delay(300)
                continue
            }
            val frame = withContext(Dispatchers.Default) { cap.latest() }
            if (frame == null) {
                delay(100)
                continue
            }
            val now = SystemClock.uptimeMillis()

            if (shown.isNotEmpty()) {
                var changed = withContext(Dispatchers.Default) {
                    FrameTools.changed(baseline, FrameTools.signature(frame, masks(shown)))
                }
                if (!changed && liveMode && now - lastPeek > PEEK_INTERVAL_MS) {
                    lastPeek = now
                    val peek = cleanFrame(cap)
                    changed = peek == null || withContext(Dispatchers.Default) {
                        FrameTools.changed(clean, FrameTools.signature(peek, ignored()))
                    }
                    if (!changed) overlay.show(shown)
                }
                if (!changed) {
                    delay(INTERVAL_MS)
                    continue
                }
                overlay.clear()
                shown = emptyList()
                baseline = null
                previous = null
                if (!liveMode) {
                    deactivate()
                    return
                }
                unstableSince = now
                delay(120)
                continue
            }

            if (translatedOnce && !liveMode) {
                deactivate()
                return
            }

            val signature = withContext(Dispatchers.Default) {
                FrameTools.signature(frame, ignored())
            }
            if (baseline != null && !FrameTools.changed(baseline, signature)) {
                delay(INTERVAL_MS)
                continue
            }
            if (unstableSince == 0L) unstableSince = now
            if (liveMode && (previous == null || FrameTools.changed(previous, signature)) &&
                now - unstableSince < MAX_UNSTABLE_MS
            ) {
                previous = signature // still scrolling / animating: wait for it to settle
                delay(STABLE_WAIT_MS)
                continue
            }

            bubble.setBusy(true)
            val items = try {
                translateFrame(frame, source, target, script)
            } catch (e: Exception) {
                Log.e(TAG, "OCR/translation failed", e)
                emptyList()
            } finally {
                bubble.setBusy(false)
            }
            translatedOnce = true
            previous = null
            unstableSince = 0L
            if (!TranslatorState.active) return
            if (items.isNotEmpty()) {
                TranslatorState.lastItems = items
                overlay.show(items)
                shown = items
                clean = signature
                lastPeek = SystemClock.uptimeMillis()
                baseline = withContext(Dispatchers.Default) {
                    FrameTools.signature(frame, masks(items))
                }
            } else {
                baseline = signature
                if (!liveMode) {
                    toast("No text found")
                    deactivate()
                    return
                }
            }
        }
    }

    private suspend fun translateFrame(
        frame: Bitmap, source: String, target: String, script: Script,
    ): List<TextItem> {
        val bubbleRect = bubble.screenRect()
        val crop = area?.let { Rect(it) }?.takeIf { it.intersect(0, 0, frame.width, frame.height) }
        val input = if (crop != null) {
            withContext(Dispatchers.Default) {
                Bitmap.createBitmap(frame, crop.left, crop.top, crop.width(), crop.height())
            }
        } else {
            frame
        }
        val recognized = try {
            engine.recognize(input, script)
        } finally {
            if (input !== frame) input.recycle()
        }
        if (crop != null) recognized.forEach { it.box.offset(crop.left, crop.top) }
        val found = recognized.filter { item ->
            bubbleRect == null || !Rect.intersects(bubbleRect, item.box)
        }
        if (found.isEmpty()) return emptyList()
        val translated = engine.translate(found, source, target)
        withContext(Dispatchers.Default) {
            for (item in translated) {
                val (bg, fg) = FrameTools.sampleColors(frame, item.box)
                item.background = bg
                item.foreground = fg
            }
        }
        return translated
    }

    /** Hides the overlay, waits for a frame without it, and returns that frame. */
    private suspend fun cleanFrame(cap: ScreenCapturer): Bitmap? {
        val before = cap.frameCount
        overlay.clear()
        return withContext(Dispatchers.Default) { cap.awaitFrameAfter(before) }
    }

    /** Parts of the screen that change detection must not look at. */
    private fun ignored(): List<Rect> = listOfNotNull(bubble.screenRect()) + outsideArea()

    /** Four rectangles covering everything around [area], so changes there are ignored. */
    private fun outsideArea(): List<Rect> {
        val a = area ?: return emptyList()
        val (w, h) = screenSize()
        val big = maxOf(w, h) * 2
        return listOf(
            Rect(-big, -big, big, a.top),
            Rect(-big, a.bottom, big, big),
            Rect(-big, a.top, a.left, a.bottom),
            Rect(a.right, a.top, big, a.bottom),
        )
    }

    private fun masks(items: List<TextItem>): List<Rect> =
        items.map { Rect(it.box) } + ignored()

    // ------------------------------------------------------------------ windows
    private fun attachOverlay() {
        if (overlayAttached) return
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            // Android 12+ only lets touches pass through overlays that are at most 80% opaque.
            alpha = OVERLAY_ALPHA
            if (Build.VERSION.SDK_INT >= 28) {
                layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            }
        }
        overlay.visibility = View.VISIBLE
        windowManager.addView(overlay, params)
        overlayAttached = true
    }

    private fun detachOverlay() {
        if (!overlayAttached) return
        windowManager.removeView(overlay)
        overlayAttached = false
    }

    private fun openMenu() {
        val active = TranslatorState.active
        val items = listOf(
            SmartMenu.Item(if (active && liveMode) "⏸  Stop live translation" else "▶  Live translate") {
                if (active && liveMode) deactivate() else {
                    deactivate()
                    activate(live = true)
                }
            },
            SmartMenu.Item("⚡  Translate once") {
                deactivate()
                activate(live = false)
            },
            SmartMenu.Item("▣  Translate an area…") { pickArea() },
            SmartMenu.Item("☰  Show text / copy") { showTextPanel() },
            SmartMenu.Item("⇄  Swap languages") { swapLanguages() },
            SmartMenu.Item("🌐  To: ${Languages.displayName(prefs.targetLang)}…") { openSettings() },
            SmartMenu.Item("✕  Close bubble") { stopSelf() },
        )
        bubble.setBusy(false)
        menu.show(bubble.anchorX, bubble.anchorY, items)
    }

    private fun swapLanguages() {
        val source = prefs.sourceLang
        val target = prefs.targetLang
        if (source == Prefs.AUTO) {
            toast("Pick a source language in settings to swap")
            return
        }
        prefs.sourceLang = target
        prefs.targetLang = source
        toast("${Languages.displayName(target)} → ${Languages.displayName(source)}")
        if (TranslatorState.active) restartLoop()
    }

    private fun openSettings() {
        startActivity(
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }

    // ------------------------------------------------------------- notification
    private fun createChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID, getString(R.string.channel_name), NotificationManager.IMPORTANCE_LOW,
        )
        manager.createNotificationChannel(channel)
    }

    private fun servicePending(action: String, code: Int): PendingIntent =
        PendingIntent.getService(
            this, code, Intent(this, TranslatorService::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

    private fun buildNotification(): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE,
        )
        val text = if (TranslatorState.active) R.string.notif_active else R.string.notif_idle
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_translate)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(text))
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(0, getString(R.string.action_toggle), servicePending(ACTION_TOGGLE, 1))
            .addAction(0, getString(R.string.action_close), servicePending(ACTION_STOP, 2))
            .build()
    }

    private fun startInForeground(withProjection: Boolean) {
        val type = when {
            Build.VERSION.SDK_INT >= 34 && withProjection ->
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE or
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            Build.VERSION.SDK_INT >= 34 -> ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            Build.VERSION.SDK_INT >= 29 && withProjection ->
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
            else -> 0
        }
        ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification(), type)
    }

    private fun updateNotification() {
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification())
    }

    private fun refreshTile() {
        TileService.requestListeningState(
            this, ComponentName(this, TranslateTileService::class.java),
        )
    }

    // ------------------------------------------------------------------ helpers
    private fun screenSize(): Pair<Int, Int> {
        return if (Build.VERSION.SDK_INT >= 30) {
            val bounds = windowManager.maximumWindowMetrics.bounds
            bounds.width() to bounds.height()
        } else {
            val metrics = android.util.DisplayMetrics()
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay.getRealMetrics(metrics)
            metrics.widthPixels to metrics.heightPixels
        }
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        val (w, h) = screenSize()
        capturer?.resize(w, h)
        bubble.keepOnScreen()
        areaSelector.dismiss()
        if (TranslatorState.active) {
            area = null // the selected box no longer matches the rotated screen
            restartLoop()
        }
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    override fun onDestroy() {
        TranslatorState.active = false
        TranslatorState.serviceRunning = false
        loopJob?.cancel()
        menu.dismiss()
        areaSelector.dismiss()
        bubble.hide()
        detachOverlay()
        capturer?.release()
        projection?.stop()
        engine.close()
        scope.cancel()
        refreshTile()
        super.onDestroy()
    }

    companion object {
        private const val TAG = "TranslatorService"
        private const val CHANNEL_ID = "floating_translator"
        private const val NOTIFICATION_ID = 42
        private const val INTERVAL_MS = 500L
        private const val STABLE_WAIT_MS = 250L
        private const val MAX_UNSTABLE_MS = 2000L
        private const val PEEK_INTERVAL_MS = 2500L
        private const val OVERLAY_ALPHA = 0.8f

        const val ACTION_SHOW = "com.omniview.translator.SHOW"
        const val ACTION_TOGGLE = "com.omniview.translator.TOGGLE"
        const val ACTION_TRANSLATE_ONCE = "com.omniview.translator.ONCE"
        const val ACTION_TRANSLATE_AREA = "com.omniview.translator.AREA"
        const val ACTION_STOP = "com.omniview.translator.STOP"
        const val ACTION_SETTINGS_CHANGED = "com.omniview.translator.SETTINGS_CHANGED"
        const val ACTION_PROJECTION_RESULT = "com.omniview.translator.PROJECTION_RESULT"
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"

        fun start(context: Context, action: String = ACTION_SHOW) {
            val intent = Intent(context, TranslatorService::class.java).setAction(action)
            ContextCompat.startForegroundService(context, intent)
        }
    }
}
