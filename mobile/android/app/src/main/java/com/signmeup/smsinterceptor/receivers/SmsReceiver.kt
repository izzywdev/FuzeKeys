package com.signmeup.smsinterceptor.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.telephony.SmsMessage
import android.util.Log
import com.signmeup.smsinterceptor.services.ServerCommunicationService
import com.signmeup.smsinterceptor.utils.OtpExtractor
import com.signmeup.smsinterceptor.utils.PreferenceManager

class SmsReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "SmsReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) {
            return
        }

        val preferenceManager = PreferenceManager(context)
        if (!preferenceManager.isServiceEnabled()) {
            Log.d(TAG, "Service is disabled, ignoring SMS")
            return
        }

        try {
            val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
            for (message in messages) {
                processSmsMessage(context, message)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error processing SMS", e)
        }
    }

    private fun processSmsMessage(context: Context, message: SmsMessage) {
        val sender = message.displayOriginatingAddress
        val messageBody = message.messageBody
        
        Log.d(TAG, "Received SMS from: $sender")
        Log.d(TAG, "Message body: $messageBody")

        // Extract OTP from the message
        val otpCode = OtpExtractor.extractOtp(messageBody)
        
        if (otpCode != null) {
            Log.d(TAG, "Found OTP: $otpCode")
            
            // Send OTP to server
            val serviceIntent = Intent(context, ServerCommunicationService::class.java).apply {
                action = ServerCommunicationService.ACTION_SEND_OTP
                putExtra(ServerCommunicationService.EXTRA_OTP_CODE, otpCode)
                putExtra(ServerCommunicationService.EXTRA_SENDER, sender)
                putExtra(ServerCommunicationService.EXTRA_MESSAGE_BODY, messageBody)
                putExtra(ServerCommunicationService.EXTRA_TIMESTAMP, System.currentTimeMillis())
            }
            
            context.startService(serviceIntent)
        } else {
            Log.d(TAG, "No OTP found in message")
        }
    }
} 