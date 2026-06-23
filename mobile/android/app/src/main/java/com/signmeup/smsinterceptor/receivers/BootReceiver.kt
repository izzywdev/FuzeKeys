package com.signmeup.smsinterceptor.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat
import com.signmeup.smsinterceptor.services.ServerCommunicationService
import com.signmeup.smsinterceptor.utils.PreferenceManager

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) {
            return
        }

        Log.d(TAG, "Device boot completed, checking if service should be restarted")

        val preferenceManager = PreferenceManager(context)
        if (preferenceManager.isServiceEnabled() && preferenceManager.isConfigured()) {
            Log.d(TAG, "Restarting SMS interceptor service after boot")
            
            val serviceIntent = Intent(context, ServerCommunicationService::class.java)
            ContextCompat.startForegroundService(context, serviceIntent)
        } else {
            Log.d(TAG, "Service not enabled or not configured, skipping restart")
        }
    }
} 