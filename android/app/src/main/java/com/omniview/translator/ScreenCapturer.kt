package com.omniview.translator

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import kotlinx.coroutines.delay

/**
 * Mirrors the whole screen into an [ImageReader] and hands out the latest frame as a Bitmap.
 *
 * A VirtualDisplay only produces frames when the screen content changes, so the most recent
 * bitmap is cached and returned while the screen is static.
 */
class ScreenCapturer(
    private val projection: MediaProjection,
    private var width: Int,
    private var height: Int,
    private val densityDpi: Int,
) {
    private val thread = HandlerThread("screen-capture").apply { start() }
    private val handler = Handler(thread.looper)
    private val lock = Object()

    private var reader: ImageReader? = null
    private var display: VirtualDisplay? = null
    private var pending: Image? = null
    private var cached: Bitmap? = null

    @Volatile
    var frameCount = 0L
        private set

    fun start() {
        reader = newReader()
        display = projection.createVirtualDisplay(
            "omniview-capture", width, height, densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader!!.surface, null, handler,
        )
    }

    @SuppressLint("WrongConstant")
    private fun newReader(): ImageReader =
        ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 3).apply {
            setOnImageAvailableListener({ r ->
                val image = try {
                    r.acquireLatestImage()
                } catch (e: IllegalStateException) {
                    null
                } ?: return@setOnImageAvailableListener
                synchronized(lock) {
                    pending?.close()
                    pending = image
                    frameCount++
                }
            }, handler)
        }

    /** Called after rotation: resize the mirror to the new screen size. */
    fun resize(newWidth: Int, newHeight: Int) {
        if (newWidth == width && newHeight == height) return
        width = newWidth
        height = newHeight
        val old = reader
        synchronized(lock) {
            pending?.close()
            pending = null
            cached = null
        }
        reader = newReader()
        display?.resize(width, height, densityDpi)
        display?.surface = reader!!.surface
        old?.close()
    }

    /** Latest screen frame, or null if nothing has been captured yet. */
    fun latest(): Bitmap? {
        val image = synchronized(lock) {
            val img = pending
            pending = null
            img
        } ?: return cached
        try {
            cached = image.toBitmap()
        } finally {
            image.close()
        }
        return cached
    }

    /** Waits until a frame newer than [since] arrives (e.g. after hiding our overlay). */
    suspend fun awaitFrameAfter(since: Long, timeoutMs: Long = 400): Bitmap? {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (frameCount <= since && SystemClock.uptimeMillis() < deadline) delay(16)
        delay(16)
        return latest()
    }

    fun release() {
        display?.release()
        display = null
        synchronized(lock) {
            pending?.close()
            pending = null
        }
        reader?.close()
        reader = null
        thread.quitSafely()
    }

    private fun Image.toBitmap(): Bitmap {
        val plane = planes[0]
        val pixelStride = plane.pixelStride
        val rowPadding = plane.rowStride - pixelStride * width
        val padded = Bitmap.createBitmap(
            width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888,
        )
        padded.copyPixelsFromBuffer(plane.buffer)
        if (padded.width == width) return padded
        val cropped = Bitmap.createBitmap(padded, 0, 0, width, height)
        padded.recycle()
        return cropped
    }
}
