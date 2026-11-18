package com.omniview.translator

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.view.View

/** Full-screen, touch-through view that paints translations over the original text. */
class TranslationOverlayView(context: Context) : View(context) {
    private var items: List<TextItem> = emptyList()
    private val background = Paint(Paint.ANTI_ALIAS_FLAG)
    private val textPaint = TextPaint(Paint.ANTI_ALIAS_FLAG)
    private val location = IntArray(2)
    private val density = resources.displayMetrics.density

    fun show(newItems: List<TextItem>) {
        items = newItems
        invalidate()
    }

    fun clear() {
        items = emptyList()
        invalidate()
    }

    val isEmpty: Boolean get() = items.isEmpty()

    override fun onDraw(canvas: Canvas) {
        if (items.isEmpty()) return
        // Boxes are in screen pixels; the window may be offset (status bar, cutout).
        getLocationOnScreen(location)
        canvas.save()
        canvas.translate(-location[0].toFloat(), -location[1].toFloat())
        val pad = 3 * density
        for (item in items) {
            val box = RectF(item.box)
            box.inset(-pad, -pad)
            background.color = item.background
            canvas.drawRoundRect(box, pad, pad, background)
            drawFitted(canvas, item.translated, item.box, item.foreground)
        }
        canvas.restore()
    }

    private fun drawFitted(canvas: Canvas, text: String, box: Rect, color: Int) {
        val width = box.width().coerceAtLeast(1)
        textPaint.color = color
        var low = 7f * density
        var high = (box.height().toFloat()).coerceIn(low, 40f * density)
        var bestSize = low
        // Binary search for the largest text size that fits the box.
        repeat(8) {
            val mid = (low + high) / 2
            if (buildLayout(text, mid, width).height <= box.height()) {
                bestSize = mid
                low = mid
            } else {
                high = mid
            }
        }
        // StaticLayout keeps a reference to the paint, so rebuild at the chosen size.
        val best = buildLayout(text, bestSize, width)
        canvas.save()
        canvas.clipRect(box.left - 3 * density, box.top - 3 * density,
            box.right + 3 * density, box.bottom + 3 * density)
        val top = box.top + ((box.height() - best.height) / 2f).coerceAtLeast(0f)
        canvas.translate(box.left.toFloat(), top)
        best.draw(canvas)
        canvas.restore()
    }

    private fun buildLayout(text: String, size: Float, width: Int): StaticLayout {
        textPaint.textSize = size
        return StaticLayout.Builder.obtain(text, 0, text.length, textPaint, width)
            .setAlignment(Layout.Alignment.ALIGN_NORMAL)
            .setIncludePad(false)
            .setLineSpacing(0f, 1f)
            .build()
    }
}
