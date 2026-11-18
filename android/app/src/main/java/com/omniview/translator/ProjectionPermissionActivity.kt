package com.omniview.translator

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle

/** Invisible activity that shows Android's screen-capture consent dialog once per session. */
class ProjectionPermissionActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState != null) return
        val manager = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val intent = if (Build.VERSION.SDK_INT >= 34) {
            // Ask for the whole screen (the overlay must follow whatever app is in front).
            manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
        } else {
            manager.createScreenCaptureIntent()
        }
        @Suppress("DEPRECATION")
        startActivityForResult(intent, REQUEST_CODE)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION")
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_CODE) {
            val result = Intent(this, TranslatorService::class.java)
                .setAction(TranslatorService.ACTION_PROJECTION_RESULT)
                .putExtra(TranslatorService.EXTRA_RESULT_CODE, if (resultCode == RESULT_OK) resultCode else 0)
                .putExtra(TranslatorService.EXTRA_RESULT_DATA, data)
            // The service is already a foreground service and we are in the foreground,
            // so a plain startService is allowed here.
            startService(result)
        }
        finish()
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }

    companion object {
        private const val REQUEST_CODE = 7
    }
}
