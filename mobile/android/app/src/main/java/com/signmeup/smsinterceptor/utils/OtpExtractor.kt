package com.signmeup.smsinterceptor.utils

import java.util.regex.Pattern

object OtpExtractor {

    // Common OTP patterns
    private val otpPatterns = listOf(
        // 4-8 digit numbers
        Pattern.compile("\\b(\\d{4,8})\\b"),
        // Numbers with specific keywords
        Pattern.compile("(?i)(?:code|otp|pin|verification|confirm).*?(\\d{4,8})"),
        Pattern.compile("(?i)(\\d{4,8}).*?(?:code|otp|pin|verification|confirm)"),
        // Alphanumeric codes (common in some services)
        Pattern.compile("\\b([A-Z0-9]{4,8})\\b"),
        // Codes with separators
        Pattern.compile("\\b(\\d{2,4}[-\\s]\\d{2,4})\\b"),
        // Specific patterns for common services
        Pattern.compile("(?i)your\\s+(?:code|otp|pin)\\s+is:?\\s*(\\d{4,8})"),
        Pattern.compile("(?i)verification\\s+code:?\\s*(\\d{4,8})"),
        Pattern.compile("(?i)(\\d{4,8})\\s+is\\s+your\\s+(?:code|otp|pin)"),
        // WhatsApp style
        Pattern.compile("(?i)whatsapp.*?(\\d{6})"),
        // Google style
        Pattern.compile("(?i)google.*?(\\d{6})"),
        // Facebook/Meta style
        Pattern.compile("(?i)(?:facebook|meta).*?(\\d{6})"),
        // Bank/financial patterns
        Pattern.compile("(?i)(?:bank|pay|wallet).*?(\\d{4,6})"),
        // Generic numeric patterns in brackets or quotes
        Pattern.compile("[\"'`]([0-9]{4,8})[\"'`]"),
        Pattern.compile("\\[([0-9]{4,8})\\]"),
        Pattern.compile("\\(([0-9]{4,8})\\)")
    )

    // Keywords that typically indicate OTP messages
    private val otpKeywords = listOf(
        "otp", "code", "verification", "verify", "confirm", "pin", "passcode",
        "security", "auth", "login", "signin", "signup", "register", "activate"
    )

    // Sender patterns that commonly send OTPs
    private val commonOtpSenders = listOf(
        "google", "facebook", "whatsapp", "telegram", "signal", "twitter", "instagram",
        "amazon", "paypal", "uber", "lyft", "airbnb", "netflix", "spotify",
        "bank", "visa", "mastercard", "amex", "chase", "wells", "citi"
    )

    /**
     * Extract OTP from SMS message body
     */
    fun extractOtp(messageBody: String): String? {
        if (messageBody.isBlank()) return null

        // First check if message contains OTP keywords
        val containsOtpKeywords = otpKeywords.any { keyword ->
            messageBody.contains(keyword, ignoreCase = true)
        }

        // Try each pattern
        for (pattern in otpPatterns) {
            val matcher = pattern.matcher(messageBody)
            while (matcher.find()) {
                val code = matcher.group(1)?.trim()
                if (code != null && isValidOtp(code, containsOtpKeywords)) {
                    return cleanOtpCode(code)
                }
            }
        }

        return null
    }

    /**
     * Check if sender is likely to send OTPs
     */
    fun isLikelyOtpSender(sender: String?): Boolean {
        if (sender.isNullOrBlank()) return false
        
        val senderLower = sender.lowercase()
        
        // Check if sender matches common OTP senders
        return commonOtpSenders.any { commonSender ->
            senderLower.contains(commonSender)
        } || 
        // Check for short numeric senders (common for OTP services)
        sender.matches(Regex("^\\d{3,6}$")) ||
        // Check for alphanumeric short codes
        sender.matches(Regex("^[A-Z0-9]{2,8}$"))
    }

    /**
     * Validate if extracted code is likely an OTP
     */
    private fun isValidOtp(code: String, hasOtpKeywords: Boolean): Boolean {
        // Remove any non-alphanumeric characters for validation
        val cleanCode = code.replace(Regex("[^A-Za-z0-9]"), "")
        
        // Must be 4-8 characters
        if (cleanCode.length !in 4..8) return false
        
        // If message has OTP keywords, be more lenient
        if (hasOtpKeywords) {
            return true
        }
        
        // For messages without clear OTP keywords, be more strict
        // Avoid common false positives
        val falsePositives = listOf(
            "1234", "0000", "9999", "1111", "2222", "3333", "4444", "5555", 
            "6666", "7777", "8888", "0123", "1000", "2000", "3000", "4000",
            "5000", "6000", "7000", "8000", "9000"
        )
        
        if (falsePositives.contains(cleanCode)) return false
        
        // Numeric codes should not be all the same digit
        if (cleanCode.all { it == cleanCode[0] }) return false
        
        // Should contain at least some variation for longer codes
        if (cleanCode.length >= 6) {
            val uniqueChars = cleanCode.toSet().size
            if (uniqueChars < 2) return false
        }
        
        return true
    }

    /**
     * Clean and format OTP code
     */
    private fun cleanOtpCode(code: String): String {
        // Remove any spaces, dashes, or other separators
        return code.replace(Regex("[\\s\\-_]"), "").uppercase()
    }

    /**
     * Enhanced OTP extraction with context analysis
     */
    fun extractOtpWithContext(messageBody: String, sender: String?): OtpResult? {
        val otp = extractOtp(messageBody)
        if (otp == null) return null
        
        val confidence = calculateConfidence(messageBody, sender, otp)
        
        return OtpResult(
            code = otp,
            confidence = confidence,
            sender = sender,
            messageBody = messageBody,
            extractedAt = System.currentTimeMillis()
        )
    }

    /**
     * Calculate confidence score for extracted OTP
     */
    private fun calculateConfidence(messageBody: String, sender: String?, otp: String): Float {
        var confidence = 0.5f // Base confidence
        
        // Increase confidence if message contains OTP keywords
        val otpKeywordCount = otpKeywords.count { keyword ->
            messageBody.contains(keyword, ignoreCase = true)
        }
        confidence += otpKeywordCount * 0.1f
        
        // Increase confidence for known OTP senders
        if (isLikelyOtpSender(sender)) {
            confidence += 0.2f
        }
        
        // Increase confidence for common OTP length (6 digits)
        if (otp.length == 6 && otp.all { it.isDigit() }) {
            confidence += 0.1f
        }
        
        // Decrease confidence for very common patterns
        if (otp.matches(Regex("\\d{4}")) && messageBody.length > 50) {
            confidence -= 0.1f
        }
        
        return confidence.coerceIn(0f, 1f)
    }

    data class OtpResult(
        val code: String,
        val confidence: Float,
        val sender: String?,
        val messageBody: String,
        val extractedAt: Long
    )
} 