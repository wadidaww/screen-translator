package com.omniview.translator

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.Rect
import android.os.Build
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import kotlin.math.max
import kotlin.math.min

/**
 * Full-screen dimmed layer where the user drags a box around the text to translate.
 * Reports the box in screen pixels, or null when the user just taps (cancel).
 */
class AreaSelector(
    private val context: Context,
    private val windowManager: WindowManager,
) {
    private var view: SelectView? = null

    val isShowing: Boolean get() = view != null

    fun show(onDone: (Rect?) -> Unit) {
        dismiss()
        val selectView = SelectView(context) { rect ->
            dismiss()
            onDone(rect)
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            if (Build.VERSION.SDK_INT >= 28) {
                layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            }
        }
        windowManager.addView(selectView, params)
        view = selectView
    }

    fun dismiss() {
        view?.let { windowManager.removeView(it) }
        view = null
    }

    @SuppressLint("ViewConstructor", "ClickableViewAccessibility")
    private class SelectView(
        context: Context,
        private val onDone: (Rect?) -> Unit,
    ) : View(context) {
        private val density = resources.displayMetrics.density
        private val dim = Paint().apply { color = Color.argb(110, 0, 0, 0) }
        private val clearPaint = Paint().apply {
            xfermode = PorterDuffXfermode(PorterDuff.Mode.CLEAR)
        }
        private val border = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 2 * density
            color = Color.rgb(66, 165, 245)
        }
        private val hintPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = 16 * density
        }
        private val hintBg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(200, 0, 0, 0) }
        private val location = IntArray(2)
        private var startX = 0f
        private var startY = 0f
        private var current: Rect? = null

        init {
            setLayerType(LAYER_TYPE_HARDWARE, null) // needed for the CLEAR "hole"
        }

        override fun onDraw(canvas: Canvas) {
            canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), dim)
            getLocationOnScreen(location)
            current?.let { screen ->
                val local = Rect(screen).apply { offset(-location[0], -location[1]) }
                canvas.drawRect(local, clearPaint)
                canvas.drawRect(local, border)
            }
            if (current == null) drawHint(canvas)
        }

        private fun drawHint(canvas: Canvas) {
            val text = "Drag a box around the text to translate.\nTap anywhere to cancel."
            val textWidth = (width - 48 * density).toInt().coerceAtLeast(1)
            val layout = StaticLayout.Builder.obtain(text, 0, text.length, hintPaint, textWidth)
                .setAlignment(Layout.Alignment.ALIGN_CENTER)
                .build()
            val top = height / 3f
            val pad = 12 * density
            canvas.drawRoundRect(
                24 * density - pad, top - pad, 24 * density + textWidth + pad,
                top + layout.height + pad, pad, pad, hintBg,
            )
            canvas.save()
            canvas.translate(24 * density, top)
            layout.draw(canvas)
            canvas.restore()
        }

        override fun onTouchEvent(event: MotionEvent): Boolean {
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = event.rawX
                    startY = event.rawY
                    current = null
                }
                MotionEvent.ACTION_MOVE -> {
                    current = Rect(
                        min(startX, event.rawX).toInt(), min(startY, event.rawY).toInt(),
                        max(startX, event.rawX).toInt(), max(startY, event.rawY).toInt(),
                    )
                    invalidate()
                }
                MotionEvent.ACTION_UP -> {
                    val rect = current
                    val minSize = (24 * density).toInt()
                    onDone(if (rect != null && rect.width() >= minSize && rect.height() >= minSize) rect else null)
                }
                MotionEvent.ACTION_CANCEL -> onDone(null)
            }
            return true
        }
    }
}
