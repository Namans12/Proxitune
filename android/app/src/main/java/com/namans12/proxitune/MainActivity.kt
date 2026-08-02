package com.namans12.proxitune

import android.Manifest
import android.app.Activity
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {
    private data class Sample(val rssi: Int, val timeMs: Long)

    private lateinit var pcUrl: EditText
    private lateinit var token: EditText
    private lateinit var echoTarget: EditText
    private lateinit var googleTarget: EditText
    private lateinit var status: TextView
    private lateinit var discovered: TextView
    private lateinit var startButton: Button
    private val samples = ConcurrentHashMap<String, Sample>()
    private val seenDevices = ConcurrentHashMap<String, String>()
    private val mainHandler = Handler(Looper.getMainLooper())
    private var scheduler: ScheduledExecutorService? = null
    private var running = false
    private var bleScanner: BluetoothLeScanner? = null

    private val bluetoothAdapter: BluetoothAdapter by lazy {
        (getSystemService(BLUETOOTH_SERVICE) as BluetoothManager).adapter
    }

    private val classicReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != BluetoothDevice.ACTION_FOUND) return
            val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE) ?: return
            val rssi = intent.getShortExtra(BluetoothDevice.EXTRA_RSSI, Short.MIN_VALUE).toInt()
            val discoveredName = intent.getStringExtra(BluetoothDevice.EXTRA_NAME)
            remember(device, rssi, discoveredName)
        }
    }

    private val bleCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            remember(result.device, result.rssi, result.scanRecord?.deviceName)
        }

        override fun onScanFailed(errorCode: Int) {
            updateStatus("BLE scan failed: $errorCode")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildView())
        requestBluetoothPermissions()
    }

    private fun buildView(): LinearLayout {
        fun field(hint: String, value: String): EditText = EditText(this).apply {
            this.hint = hint
            setText(value)
            setSingleLine(true)
        }

        pcUrl = field("Windows URL", "http://192.168.1.100:8765")
        token = field("Controller token", "")
        echoTarget = field("Echo name or Bluetooth address", "Echo")
        googleTarget = field("Google Home name or Bluetooth address", "Google Home")
        status = TextView(this).apply { text = "Configure the PC URL and speaker names." }
        discovered = TextView(this).apply { text = "Seen devices will appear here while scanning." }
        startButton = Button(this).apply {
            text = "Start proximity scanning"
            setOnClickListener { if (running) stopScanning() else startScanning() }
        }

        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 28, 28, 28)
            addView(TextView(this@MainActivity).apply { text = "ProxiTune Companion" })
            addView(TextView(this@MainActivity).apply { text = "The phone scans for both speakers and sends RSSI to Windows." })
            addView(pcUrl)
            addView(token)
            addView(echoTarget)
            addView(googleTarget)
            addView(startButton)
            addView(status)
            addView(discovered)
        }
    }

    private fun requestBluetoothPermissions() {
        val permissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.ACCESS_FINE_LOCATION,
            )
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        val missing = permissions.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) requestPermissions(missing.toTypedArray(), 10)
    }

    private fun startScanning() {
        if (checkSelfPermissionForBluetooth() != PackageManager.PERMISSION_GRANTED) {
            updateStatus("Bluetooth permission is required")
            requestBluetoothPermissions()
            return
        }
        if (!bluetoothAdapter.isEnabled) {
            updateStatus("Turn on Bluetooth, then try again")
            return
        }
        running = true
        startButton.text = "Stop proximity scanning"
        registerClassicReceiver()
        try {
            bleScanner = bluetoothAdapter.bluetoothLeScanner
            bleScanner?.startScan(bleCallback)
            bluetoothAdapter.startDiscovery()
        } catch (security: SecurityException) {
            updateStatus("Bluetooth permission was denied")
            stopScanning()
            return
        }
        scheduler = Executors.newScheduledThreadPool(2).also { executor ->
            executor.scheduleAtFixedRate({ sendReadings() }, 0, 2, TimeUnit.SECONDS)
            executor.scheduleAtFixedRate({ restartClassicDiscovery() }, 0, 12, TimeUnit.SECONDS)
        }
        updateStatus("Scanning… speakers must be discoverable for Classic Bluetooth RSSI")
    }

    private fun stopScanning() {
        running = false
        scheduler?.shutdownNow()
        scheduler = null
        try {
            bleScanner?.stopScan(bleCallback)
            if (bluetoothAdapter.isDiscovering) bluetoothAdapter.cancelDiscovery()
            unregisterReceiver(classicReceiver)
        } catch (_: Exception) {
            // Safe cleanup when Android has already stopped a scan.
        }
        startButton.text = "Start proximity scanning"
        updateStatus("Scanning stopped")
    }

    private fun restartClassicDiscovery() {
        if (!running) return
        try {
            if (bluetoothAdapter.isDiscovering) bluetoothAdapter.cancelDiscovery()
            bluetoothAdapter.startDiscovery()
        } catch (_: SecurityException) {
            updateStatus("Bluetooth permission was denied")
        }
    }

    private fun registerClassicReceiver() {
        val filter = IntentFilter(BluetoothDevice.ACTION_FOUND)
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(classicReceiver, filter, RECEIVER_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(classicReceiver, filter)
        }
    }

    private fun remember(device: BluetoothDevice, rssi: Int, discoveredName: String? = null) {
        val name = discoveredName?.takeIf { it.isNotBlank() } ?: try { device.name ?: "" } catch (_: SecurityException) { "" }
        val address = device.address
        seenDevices[address] = "${name.ifBlank { "(unnamed)" }} · $address · $rssi dBm"
        val echo = echoTarget.text.toString()
        val google = googleTarget.text.toString()
        when {
            matches(name, address, echo) -> samples["echo"] = Sample(rssi, System.currentTimeMillis())
            matches(name, address, google) -> samples["google"] = Sample(rssi, System.currentTimeMillis())
        }
        updateStatus("Echo ${samples["echo"]?.rssi ?: "—"} dBm · Google ${samples["google"]?.rssi ?: "—"} dBm")
    }

    private fun matches(name: String, address: String, target: String): Boolean {
        val needle = target.trim().lowercase(Locale.US)
        return needle.isNotEmpty() && (name.lowercase(Locale.US).contains(needle) || address.equals(needle, ignoreCase = true))
    }

    private fun sendReadings() {
        val now = System.currentTimeMillis()
        val echo = samples["echo"]?.takeIf { now - it.timeMs <= 8_000 }
        val google = samples["google"]?.takeIf { now - it.timeMs <= 8_000 }
        if (echo == null || google == null) return
        val url = pcUrl.text.toString().trimEnd('/')
        val secret = token.text.toString()
        if (url.isBlank() || secret.isBlank()) return
        val body = "{\"readings\":{\"echo\":${echo.rssi},\"google\":${google.rssi}}}"
        try {
            val endpoint = URL("$url/proximity?token=${URLEncoder.encode(secret, "UTF-8")}")
            val connection = endpoint.openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.connectTimeout = 2_000
            connection.readTimeout = 2_000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            connection.disconnect()
            if (code !in 200..299) updateStatus("Windows controller returned HTTP $code")
        } catch (error: Exception) {
            updateStatus("Controller unavailable: ${error.javaClass.simpleName}")
        }
    }

    private fun checkSelfPermissionForBluetooth(): Int {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN)
        } else {
            checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    private fun updateStatus(message: String) {
        mainHandler.post {
            if (::status.isInitialized) status.text = message
            if (::discovered.isInitialized) {
                val lines = seenDevices.values.sorted().takeLast(12)
                discovered.text = if (lines.isEmpty()) "No Bluetooth devices seen yet." else "Seen devices:\n" + lines.joinToString("\n")
            }
        }
    }

    override fun onDestroy() {
        if (running) stopScanning()
        super.onDestroy()
    }
}
