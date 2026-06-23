package com.signmeup.smsinterceptor

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.signmeup.smsinterceptor.databinding.ActivityMainBinding
import com.signmeup.smsinterceptor.services.ServerCommunicationService
import com.signmeup.smsinterceptor.utils.PreferenceManager

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var preferenceManager: PreferenceManager

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.values.all { it }
        if (allGranted) {
            startServices()
            updateUI()
        } else {
            Toast.makeText(this, "SMS permissions are required for the app to work", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        preferenceManager = PreferenceManager(this)
        
        setupUI()
        checkPermissions()
    }

    private fun setupUI() {
        binding.apply {
            // Server URL configuration
            editTextServerUrl.setText(preferenceManager.getServerUrl())
            
            buttonSaveSettings.setOnClickListener {
                val serverUrl = editTextServerUrl.text.toString().trim()
                if (serverUrl.isNotEmpty()) {
                    preferenceManager.setServerUrl(serverUrl)
                    Toast.makeText(this@MainActivity, "Settings saved", Toast.LENGTH_SHORT).show()
                    restartService()
                } else {
                    Toast.makeText(this@MainActivity, "Please enter a valid server URL", Toast.LENGTH_SHORT).show()
                }
            }
            
            switchServiceEnabled.setOnCheckedChangeListener { _, isChecked ->
                preferenceManager.setServiceEnabled(isChecked)
                if (isChecked) {
                    startServices()
                } else {
                    stopServices()
                }
                updateUI()
            }
            
            buttonTestConnection.setOnClickListener {
                testServerConnection()
            }
        }
        
        updateUI()
    }

    private fun checkPermissions() {
        val permissions = mutableListOf<String>().apply {
            add(Manifest.permission.RECEIVE_SMS)
            add(Manifest.permission.READ_SMS)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        val missingPermissions = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missingPermissions.isNotEmpty()) {
            requestPermissionLauncher.launch(missingPermissions.toTypedArray())
        } else {
            startServices()
        }
    }

    private fun startServices() {
        if (preferenceManager.isServiceEnabled() && hasRequiredPermissions()) {
            val serviceIntent = Intent(this, ServerCommunicationService::class.java)
            ContextCompat.startForegroundService(this, serviceIntent)
        }
    }

    private fun stopServices() {
        val serviceIntent = Intent(this, ServerCommunicationService::class.java)
        stopService(serviceIntent)
    }

    private fun restartService() {
        stopServices()
        if (preferenceManager.isServiceEnabled()) {
            startServices()
        }
    }

    private fun hasRequiredPermissions(): Boolean {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.READ_SMS) == PackageManager.PERMISSION_GRANTED
    }

    private fun updateUI() {
        binding.apply {
            switchServiceEnabled.isChecked = preferenceManager.isServiceEnabled()
            
            val isServiceRunning = ServerCommunicationService.isRunning()
            val hasPermissions = hasRequiredPermissions()
            
            textViewStatus.text = when {
                !hasPermissions -> "❌ Missing SMS permissions"
                !preferenceManager.isServiceEnabled() -> "⏸️ Service disabled"
                isServiceRunning -> "✅ Service running"
                else -> "⚠️ Service stopped"
            }
            
            val serverUrl = preferenceManager.getServerUrl()
            textViewServerStatus.text = if (serverUrl.isNotEmpty()) {
                "Server: $serverUrl"
            } else {
                "❌ No server configured"
            }
        }
    }

    private fun testServerConnection() {
        // This would typically test the connection to your server
        Toast.makeText(this, "Testing connection...", Toast.LENGTH_SHORT).show()
        // TODO: Implement actual connection test
    }

    override fun onResume() {
        super.onResume()
        updateUI()
    }
} 