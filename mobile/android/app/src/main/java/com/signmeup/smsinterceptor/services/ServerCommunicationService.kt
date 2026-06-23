package com.signmeup.smsinterceptor.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.signmeup.smsinterceptor.MainActivity
import com.signmeup.smsinterceptor.R
import com.signmeup.smsinterceptor.api.ApiClient
import com.signmeup.smsinterceptor.api.OtpRequest
import com.signmeup.smsinterceptor.utils.PreferenceManager
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.logging.HttpLoggingInterceptor
import java.util.concurrent.TimeUnit

class ServerCommunicationService : Service() {

    companion object {
        private const val TAG = "ServerCommService"
        private const val NOTIFICATION_ID = 1
        private const val CHANNEL_ID = "SMS_INTERCEPTOR_CHANNEL"
        
        const val ACTION_SEND_OTP = "com.signmeup.smsinterceptor.SEND_OTP"
        const val EXTRA_OTP_CODE = "otp_code"
        const val EXTRA_SENDER = "sender"
        const val EXTRA_MESSAGE_BODY = "message_body"
        const val EXTRA_TIMESTAMP = "timestamp"
        
        @Volatile
        private var isServiceRunning = false
        
        fun isRunning(): Boolean = isServiceRunning
    }

    private lateinit var preferenceManager: PreferenceManager
    private lateinit var apiClient: ApiClient
    private var webSocket: WebSocket? = null
    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate() {
        super.onCreate()
        preferenceManager = PreferenceManager(this)
        apiClient = ApiClient(preferenceManager.getServerUrl())
        
        createNotificationChannel()
        startForegroundService()
        connectToServer()
        
        isServiceRunning = true
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        intent?.let { handleIntent(it) }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        isServiceRunning = false
        webSocket?.close(1000, "Service destroyed")
        serviceScope.cancel()
        Log.d(TAG, "Service destroyed")
    }

    private fun handleIntent(intent: Intent) {
        when (intent.action) {
            ACTION_SEND_OTP -> {
                val otpCode = intent.getStringExtra(EXTRA_OTP_CODE)
                val sender = intent.getStringExtra(EXTRA_SENDER)
                val messageBody = intent.getStringExtra(EXTRA_MESSAGE_BODY)
                val timestamp = intent.getLongExtra(EXTRA_TIMESTAMP, System.currentTimeMillis())
                
                if (otpCode != null) {
                    sendOtpToServer(otpCode, sender, messageBody, timestamp)
                }
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "SMS Interceptor Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Handles SMS interception and server communication"
                setShowBadge(false)
            }
            
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun startForegroundService() {
        val notification = createNotification("Service running")
        startForeground(NOTIFICATION_ID, notification)
    }

    private fun createNotification(text: String): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("SignMeUp SMS Interceptor")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val notification = createNotification(text)
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(NOTIFICATION_ID, notification)
    }

    private fun connectToServer() {
        val serverUrl = preferenceManager.getServerUrl()
        if (serverUrl.isEmpty()) {
            Log.w(TAG, "No server URL configured")
            return
        }

        try {
            val client = OkHttpClient.Builder()
                .addInterceptor(HttpLoggingInterceptor().apply {
                    level = HttpLoggingInterceptor.Level.BASIC
                })
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .build()

            val wsUrl = serverUrl.replace("http://", "ws://").replace("https://", "wss://") + "/ws/sms-interceptor"
            val request = Request.Builder()
                .url(wsUrl)
                .build()

            webSocket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    Log.d(TAG, "WebSocket connected")
                    updateNotification("Connected to server")
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    Log.d(TAG, "Received message: $text")
                    // Handle server messages (e.g., OTP requests)
                    handleServerMessage(text)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    Log.e(TAG, "WebSocket error", t)
                    updateNotification("Connection failed")
                    // Retry connection after delay
                    serviceScope.launch {
                        delay(10000)
                        connectToServer()
                    }
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    Log.d(TAG, "WebSocket closed: $code - $reason")
                    updateNotification("Disconnected from server")
                }
            })

        } catch (e: Exception) {
            Log.e(TAG, "Error connecting to server", e)
            updateNotification("Connection error")
        }
    }

    private fun handleServerMessage(message: String) {
        // Parse server messages and handle OTP requests
        // This would typically parse JSON messages from your server
        Log.d(TAG, "Handling server message: $message")
    }

    private fun sendOtpToServer(otpCode: String, sender: String?, messageBody: String?, timestamp: Long) {
        serviceScope.launch {
            try {
                val otpRequest = OtpRequest(
                    otp = otpCode,
                    sender = sender ?: "",
                    messageBody = messageBody ?: "",
                    timestamp = timestamp,
                    deviceId = getDeviceId()
                )

                val response = apiClient.sendOtp(otpRequest)
                if (response.isSuccessful) {
                    Log.d(TAG, "OTP sent successfully")
                    updateNotification("OTP sent: $otpCode")
                } else {
                    Log.e(TAG, "Failed to send OTP: ${response.code()}")
                    updateNotification("Failed to send OTP")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error sending OTP", e)
                updateNotification("Error sending OTP")
            }
        }
    }

    private fun getDeviceId(): String {
        // Generate or retrieve a unique device ID
        return preferenceManager.getDeviceId() ?: run {
            val newDeviceId = java.util.UUID.randomUUID().toString()
            preferenceManager.setDeviceId(newDeviceId)
            newDeviceId
        }
    }
} 