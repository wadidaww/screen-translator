package com.omniview.translator

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.PixelFormat
import android.graphics.Rect
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import kotlin.math.abs

/**
 * The draggable floating button. Tap = toggle translation, long-press = smart menu.
 * It snaps to the nearest screen edge when released.
 */
@SuppressLint("ClickableViewAccessibility")
class FloatingBubble(
    private val context: Context,
    private val windowManager: WindowManager,
    private val prefs: Prefs,
    private val onTap: () -> Unit,
    private val onLongPress: () -> Unit,
) {
    private val density = context.resources.displayMetrics.density
    private val size = (56 * density).toInt()
    private val icon = ImageView(context).apply {
        setImageResource(R.drawable.ic_translate)
        val pad = (14 * density).toInt()
        setPadding(pad, pad, pad, pad)
    }
    private val spinner = ProgressBar(context).apply { visibility = View.GONE }
    private val root = FrameLayout(context).apply {
        setBackgroundResource(R.drawable.bubble_idle)
        elevation = 6 * density
        addView(icon, FrameLayout.LayoutParams(size, size))
        addView(spinner, FrameLayout.LayoutParams(size, size))
        contentDescription = "Screen translator"
    }
    private val params = WindowManager.LayoutParams(
        size, size,
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
        PixelFormat.TRANSLUCENT,
    ).apply {
        gravity = Gravity.TOP or Gravity.START
        x = prefs.bubbleX
        y = prefs.bubbleY
    }
    private var attached = false

    fun show() {
        if (attached) return
        if (params.x < 0) params.x = screenWidth() - size - (8 * density).toInt()
        root.setOnTouchListener(DragListener())
        windowManager.addView(root, params)
        attached = true
    }

    fun hide() {
        if (!attached) return
        windowManager.removeView(root)
        attached = false
    }

    fun setActive(active: Boolean) {
        root.setBackgroundResource(if (active) R.drawable.bubble_active else R.drawable.bubble_idle)
    }

    fun setBusy(busy: Boolean) {
        spinner.visibility = if (busy) View.VISIBLE else View.GONE
    }

    /** Bubble position on screen, so it can be ignored by OCR and change detection. */
    fun screenRect(): Rect? {
        if (!attached) return null
        val loc = IntArray(2)
        root.getLocationOnScreen(loc)
        return Rect(loc[0], loc[1], loc[0] + size, loc[1] + size)
    }

    /** After rotation or a resolution change, move the bubble back inside the screen. */
    fun keepOnScreen() {
        if (!attached) return
        val margin = (8 * density).toInt()
        val metrics = context.resources.displayMetrics
        val wasRight = params.x > margin
        params.x = if (wasRight) metrics.widthPixels - size - margin else margin
        params.y = params.y.coerceIn(0, (metrics.heightPixels - size).coerceAtLeast(0))
        windowManager.updateViewLayout(root, params)
        prefs.bubbleX = params.x
        prefs.bubbleY = params.y
    }

    val anchorX: Int get() = params.x
    val anchorY: Int get() = params.y

    private fun screenWidth(): Int = context.resources.displayMetrics.widthPixels

    private inner class DragListener : View.OnTouchListener {
        private val slop = ViewConfiguration.get(context).scaledTouchSlop
        private val longPressMs = ViewConfiguration.getLongPressTimeout().toLong()
        private var downX = 0f
        private var downY = 0f
        private var startX = 0
        private var startY = 0
        private var dragging = false
        private var longPressed = false
        private val longPress = Runnable {
            if (!dragging) {
                longPressed = true
                root.performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
                onLongPress()
            }
        }

        override fun onTouch(v: View, event: MotionEvent): Boolean {
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX
                    downY = event.rawY
                    startX = params.x
                    startY = params.y
                    dragging = false
                    longPressed = false
                    root.postDelayed(longPress, longPressMs)
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - downX
                    val dy = event.rawY - downY
                    if (!dragging && (abs(dx) > slop || abs(dy) > slop)) {
                        dragging = true
                        root.removeCallbacks(longPress)
                    }
                    if (dragging) {
                        params.x = (startX + dx).toInt()
                        params.y = (startY + dy).toInt()
                        windowManager.updateViewLayout(root, params)
                    }
                }
                MotionEvent.ACTION_UP -> {
                    root.removeCallbacks(longPress)
                    if (dragging) {
                        snapToEdge()
                    } else if (!longPressed) {
                        onTap()
                    }
                }
                MotionEvent.ACTION_CANCEL -> root.removeCallbacks(longPress)
            }
            return true
        }

        private fun snapToEdge() {
            val margin = (8 * density).toInt()
            val middle = params.x + size / 2
            params.x = if (middle < screenWidth() / 2) margin else screenWidth() - size - margin
            params.y = params.y.coerceAtLeast(0)
            windowManager.updateViewLayout(root, params)
            prefs.bubbleX = params.x
            prefs.bubbleY = params.y
        }
    }
}

/** Small popup next to the bubble with quick actions. */
class SmartMenu(
    private val context: Context,
    private val windowManager: WindowManager,
) {
    private val density = context.resources.displayMetrics.density
    private var view: View? = null

    data class Item(val label: String, val action: () -> Unit)

    val isShowing: Boolean get() = view != null

    fun show(anchorX: Int, anchorY: Int, items: List<Item>) {
        dismiss()
        val list = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.menu_bg)
            val pad = (8 * density).toInt()
            setPadding(pad, pad, pad, pad)
            elevation = 8 * density
        }
        for (item in items) {
            list.addView(TextView(context).apply {
                text = item.label
                textSize = 16f
                setTextColor(0xFFFFFFFF.toInt())
                val h = (14 * density).toInt()
                val v = (12 * density).toInt()
                setPadding(h, v, h, v)
                setOnClickListener {
                    dismiss()
                    item.action()
                }
            })
        }
        list.setOnTouchListener { _, event ->
            if (event.actionMasked == MotionEvent.ACTION_OUTSIDE) dismiss()
            false
        }
        val screenWidth = context.resources.displayMetrics.widthPixels
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
            PixelFormat.TRANSLUCENT,
        ).apply {
            val onLeft = anchorX < screenWidth / 2
            gravity = Gravity.TOP or (if (onLeft) Gravity.START else Gravity.END)
            x = if (onLeft) anchorX + (64 * density).toInt() else
                screenWidth - anchorX + (8 * density).toInt()
            y = anchorY
        }
        windowManager.addView(list, params)
        view = list
    }

    fun dismiss() {
        view?.let { windowManager.removeView(it) }
        view = null
    }
}
