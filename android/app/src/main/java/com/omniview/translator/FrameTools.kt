package com.omniview.translator

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Rect
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Tiny grey thumbnail of the screen plus which pixels may be compared. */
class Signature(val width: Int, val height: Int, val luma: IntArray, val valid: BooleanArray)

object FrameTools {
    private const val THUMB_WIDTH = 120
    private const val PIXEL_DIFF = 24
    private const val CHANGED_RATIO = 0.004f
    private const val MASK_MARGIN = 16

    /** Builds a signature; pixels inside [masked] (our own overlay, the bubble) are ignored. */
    fun signature(frame: Bitmap, masked: List<Rect> = emptyList()): Signature {
        val step = max(1, frame.width / THUMB_WIDTH)
        val w = frame.width / step
        val h = frame.height / step
        val thumb = Bitmap.createScaledBitmap(frame, w, h, false)
        val pixels = IntArray(w * h)
        thumb.getPixels(pixels, 0, w, 0, 0, w, h)
        if (thumb !== frame) thumb.recycle()
        val luma = IntArray(w * h) { i -> luminance(pixels[i]) }
        val valid = BooleanArray(w * h) { true }
        for (r in masked) {
            val x0 = max(0, (r.left - MASK_MARGIN) / step)
            val y0 = max(0, (r.top - MASK_MARGIN) / step)
            val x1 = min(w - 1, (r.right + MASK_MARGIN) / step + 1)
            val y1 = min(h - 1, (r.bottom + MASK_MARGIN) / step + 1)
            for (y in y0..y1) for (x in x0..x1) valid[y * w + x] = false
        }
        return Signature(w, h, luma, valid)
    }

    fun changed(previous: Signature?, current: Signature): Boolean {
        if (previous == null) return true
        if (previous.width != current.width || previous.height != current.height) return true
        var usable = 0
        var diff = 0
        for (i in current.luma.indices) {
            if (!previous.valid[i] || !current.valid[i]) continue
            usable++
            if (abs(previous.luma[i] - current.luma[i]) > PIXEL_DIFF) diff++
        }
        if (usable == 0) return false
        return diff.toFloat() / usable > CHANGED_RATIO
    }

    fun luminance(color: Int): Int =
        (Color.red(color) * 299 + Color.green(color) * 587 + Color.blue(color) * 114) / 1000

    /** Estimates (background, text) colours of a text box. */
    fun sampleColors(frame: Bitmap, box: Rect): Pair<Int, Int> {
        val ring = 4
        val outer = Rect(box.left - ring, box.top - ring, box.right + ring, box.bottom + ring)
        if (!outer.intersect(0, 0, frame.width, frame.height)) return Color.WHITE to Color.BLACK
        val inner = Rect(box)
        if (!inner.intersect(0, 0, frame.width, frame.height)) return Color.WHITE to Color.BLACK

        val border = ArrayList<Int>()
        val stepO = max(1, max(outer.width(), outer.height()) / 60)
        var x = outer.left
        while (x < outer.right) {
            border.add(frame.getPixel(x, outer.top))
            border.add(frame.getPixel(x, outer.bottom - 1))
            x += stepO
        }
        var y = outer.top
        while (y < outer.bottom) {
            border.add(frame.getPixel(outer.left, y))
            border.add(frame.getPixel(outer.right - 1, y))
            y += stepO
        }
        val bg = Color.rgb(
            median(border.map { Color.red(it) }),
            median(border.map { Color.green(it) }),
            median(border.map { Color.blue(it) }),
        )

        // Text colour: the pixels inside the box that differ most from the background.
        val inside = ArrayList<Int>()
        val stepI = max(1, max(inner.width(), inner.height()) / 80)
        y = inner.top
        while (y < inner.bottom) {
            x = inner.left
            while (x < inner.right) {
                inside.add(frame.getPixel(x, y))
                x += stepI
            }
            y += stepI
        }
        val sorted = inside.sortedByDescending { distance(it, bg) }
        val top = sorted.take(max(1, sorted.size / 10))
        var fg = Color.rgb(
            top.sumOf { Color.red(it) } / top.size,
            top.sumOf { Color.green(it) } / top.size,
            top.sumOf { Color.blue(it) } / top.size,
        )
        if (abs(luminance(fg) - luminance(bg)) < 90) {
            fg = if (luminance(bg) > 140) Color.BLACK else Color.WHITE
        }
        return bg to fg
    }

    private fun distance(a: Int, b: Int) =
        abs(Color.red(a) - Color.red(b)) + abs(Color.green(a) - Color.green(b)) +
            abs(Color.blue(a) - Color.blue(b))

    private fun median(values: List<Int>): Int {
        if (values.isEmpty()) return 255
        val sorted = values.sorted()
        return sorted[sorted.size / 2]
    }
}
