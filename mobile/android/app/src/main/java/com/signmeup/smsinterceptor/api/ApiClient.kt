package com.signmeup.smsinterceptor.api

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import java.util.concurrent.TimeUnit

class ApiClient(private val baseUrl: String) {

    private val retrofitService: ApiService by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }

        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()

        val retrofit = Retrofit.Builder()
            .baseUrl(if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/")
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        retrofit.create(ApiService::class.java)
    }

    suspend fun sendOtp(otpRequest: OtpRequest): Response<OtpResponse> {
        return retrofitService.sendOtp(otpRequest)
    }

    suspend fun registerDevice(deviceRequest: DeviceRegistrationRequest): Response<DeviceRegistrationResponse> {
        return retrofitService.registerDevice(deviceRequest)
    }

    suspend fun getOtpRequests(deviceId: String): Response<List<OtpRequestInfo>> {
        return retrofitService.getOtpRequests(deviceId)
    }

    suspend fun healthCheck(): Response<HealthResponse> {
        return retrofitService.healthCheck()
    }
}

interface ApiService {
    @POST("api/sms/otp")
    suspend fun sendOtp(@Body request: OtpRequest): Response<OtpResponse>

    @POST("api/sms/register-device")
    suspend fun registerDevice(@Body request: DeviceRegistrationRequest): Response<DeviceRegistrationResponse>

    @GET("api/sms/requests/{deviceId}")
    suspend fun getOtpRequests(@Path("deviceId") deviceId: String): Response<List<OtpRequestInfo>>

    @GET("api/health")
    suspend fun healthCheck(): Response<HealthResponse>
}

// Data classes for API requests and responses
data class OtpRequest(
    val otp: String,
    val sender: String,
    val messageBody: String,
    val timestamp: Long,
    val deviceId: String,
    val confidence: Float? = null
)

data class OtpResponse(
    val success: Boolean,
    val message: String,
    val requestId: String?
)

data class DeviceRegistrationRequest(
    val deviceId: String,
    val deviceName: String,
    val osVersion: String,
    val appVersion: String
)

data class DeviceRegistrationResponse(
    val success: Boolean,
    val message: String,
    val deviceId: String,
    val apiKey: String?
)

data class OtpRequestInfo(
    val requestId: String,
    val service: String,
    val timestamp: Long,
    val status: String,
    val timeout: Long?
)

data class HealthResponse(
    val status: String,
    val timestamp: Long,
    val version: String
) 