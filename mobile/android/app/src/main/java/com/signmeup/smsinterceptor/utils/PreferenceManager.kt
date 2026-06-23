package com.signmeup.smsinterceptor.utils

import android.content.Context
import android.content.SharedPreferences

class PreferenceManager(context: Context) {

    companion object {
        private const val PREFS_NAME = "SignMeUpSMSInterceptor"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_SERVICE_ENABLED = "service_enabled"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_API_KEY = "api_key"
        private const val KEY_LAST_OTP_TIME = "last_otp_time"
        private const val KEY_TOTAL_OTPS_SENT = "total_otps_sent"
        private const val KEY_AUTO_FORWARD_ENABLED = "auto_forward_enabled"
        private const val KEY_FILTER_ENABLED = "filter_enabled"
        private const val KEY_MIN_CONFIDENCE = "min_confidence"
    }

    private val sharedPreferences: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    // Server Configuration
    fun getServerUrl(): String = sharedPreferences.getString(KEY_SERVER_URL, "") ?: ""
    fun setServerUrl(url: String) = sharedPreferences.edit().putString(KEY_SERVER_URL, url).apply()

    fun getApiKey(): String = sharedPreferences.getString(KEY_API_KEY, "") ?: ""
    fun setApiKey(apiKey: String) = sharedPreferences.edit().putString(KEY_API_KEY, apiKey).apply()

    // Service Settings
    fun isServiceEnabled(): Boolean = sharedPreferences.getBoolean(KEY_SERVICE_ENABLED, false)
    fun setServiceEnabled(enabled: Boolean) = sharedPreferences.edit().putBoolean(KEY_SERVICE_ENABLED, enabled).apply()

    fun isAutoForwardEnabled(): Boolean = sharedPreferences.getBoolean(KEY_AUTO_FORWARD_ENABLED, true)
    fun setAutoForwardEnabled(enabled: Boolean) = sharedPreferences.edit().putBoolean(KEY_AUTO_FORWARD_ENABLED, enabled).apply()

    fun isFilterEnabled(): Boolean = sharedPreferences.getBoolean(KEY_FILTER_ENABLED, true)
    fun setFilterEnabled(enabled: Boolean) = sharedPreferences.edit().putBoolean(KEY_FILTER_ENABLED, enabled).apply()

    // Device Identity
    fun getDeviceId(): String? = sharedPreferences.getString(KEY_DEVICE_ID, null)
    fun setDeviceId(deviceId: String) = sharedPreferences.edit().putString(KEY_DEVICE_ID, deviceId).apply()

    // Statistics
    fun getLastOtpTime(): Long = sharedPreferences.getLong(KEY_LAST_OTP_TIME, 0L)
    fun setLastOtpTime(timestamp: Long) = sharedPreferences.edit().putLong(KEY_LAST_OTP_TIME, timestamp).apply()

    fun getTotalOtpsSent(): Int = sharedPreferences.getInt(KEY_TOTAL_OTPS_SENT, 0)
    fun incrementOtpsSent() {
        val current = getTotalOtpsSent()
        sharedPreferences.edit().putInt(KEY_TOTAL_OTPS_SENT, current + 1).apply()
    }

    // OTP Processing Settings
    fun getMinConfidence(): Float = sharedPreferences.getFloat(KEY_MIN_CONFIDENCE, 0.7f)
    fun setMinConfidence(confidence: Float) = sharedPreferences.edit().putFloat(KEY_MIN_CONFIDENCE, confidence).apply()

    // Helper methods
    fun isConfigured(): Boolean {
        return getServerUrl().isNotEmpty() && getDeviceId() != null
    }

    fun clearAll() {
        sharedPreferences.edit().clear().apply()
    }

    fun exportSettings(): Map<String, Any> {
        return mapOf(
            "serverUrl" to getServerUrl(),
            "serviceEnabled" to isServiceEnabled(),
            "autoForwardEnabled" to isAutoForwardEnabled(),
            "filterEnabled" to isFilterEnabled(),
            "minConfidence" to getMinConfidence(),
            "totalOtpsSent" to getTotalOtpsSent(),
            "lastOtpTime" to getLastOtpTime()
        )
    }
} 