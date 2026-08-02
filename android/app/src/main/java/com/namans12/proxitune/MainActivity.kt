package com.namans12.proxitune

import android.Manifest
import android.os.Bundle
import android.graphics.Color
import android.net.Uri
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : ComponentActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val preferences by lazy { getSharedPreferences("pairing", MODE_PRIVATE) }
    private lateinit var status: TextView
    private lateinit var connection: TextView
    private lateinit var remotePanel: LinearLayout
    private var baseUrl: String? = null
    private var token: String? = null

    private val barcodeLauncher = registerForActivityResult(ScanContract()) { result ->
        try {
            val contents = result.contents
            if (!contents.isNullOrBlank()) {
                pairFrom(contents)
            } else {
                connection.text = "QR scan cancelled. Tap Scan Windows QR Code to try again."
            }
        } catch (error: Exception) {
            connection.text = "QR scanner error: ${error.message ?: "unknown error"}"
        }
    }

    private val cameraPermissionLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) launchScanner()
        else connection.text = "Camera permission is required to scan the Windows QR code."
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        loadPairing()
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 32, 28, 28)
            setBackgroundColor(Color.rgb(248, 247, 252))
        }
        val scroll = ScrollView(this).apply { addView(root) }
        setContentView(scroll)

        root.addView(TextView(this).apply {
            text = "ProxiTune Remote"
            textSize = 30f
            setTextColor(Color.rgb(30, 30, 36))
        })
        root.addView(TextView(this).apply {
            text = "Control your laptop's speakers and media"
            textSize = 16f
            setTextColor(Color.DKGRAY)
            setPadding(0, 4, 0, 24)
        })
        val scan = Button(this).apply {
            text = "SCAN WINDOWS QR CODE"
            setOnClickListener { scanQr() }
        }
        root.addView(scan, matchParams())
        connection = TextView(this).apply {
            textSize = 14f
            setTextColor(Color.DKGRAY)
            setPadding(0, 10, 0, 16)
        }
        root.addView(connection)

        remotePanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }
        root.addView(remotePanel)
        addSection("Speaker output")
        addZone("Echo", "echo")
        addZone("Google Home", "google")
        addZone("Laptop speakers", "laptop")
        addSection("Media")
        val mediaRow = LinearLayout(this).apply { gravity = Gravity.CENTER }
        mediaRow.addView(mediaButton("⏮", "previous"), buttonParams())
        mediaRow.addView(mediaButton("▶ / ⏸", "toggle"), buttonParams())
        mediaRow.addView(mediaButton("⏭", "next"), buttonParams())
        remotePanel.addView(mediaRow)
        status = TextView(this).apply {
            textSize = 15f
            setTextColor(Color.rgb(45, 45, 50))
            setPadding(0, 22, 0, 0)
        }
        remotePanel.addView(status)
    }

    private fun addSection(title: String) {
        remotePanel.addView(TextView(this).apply {
            text = title
            textSize = 20f
            setTextColor(Color.rgb(30, 30, 36))
            setPadding(0, 18, 0, 8)
        })
    }

    private fun addZone(label: String, zone: String) {
        remotePanel.addView(Button(this).apply {
            text = label
            setOnClickListener { sendZone(zone) }
        }, matchParams())
    }

    private fun mediaButton(label: String, action: String) = Button(this).apply {
        text = label
        setOnClickListener { sendMedia(action) }
    }

    private fun matchParams() = LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, 5, 0, 5) }
    private fun buttonParams() = LinearLayout.LayoutParams(0, -2, 1f).apply { setMargins(4, 0, 4, 0) }

    private fun loadPairing() {
        baseUrl = preferences.getString("url", null)
        token = preferences.getString("token", null)
        if (baseUrl.isNullOrBlank() || token.isNullOrBlank()) {
            connection.text = "Not paired yet. Run ProxiTune on Windows, then scan its QR code."
            return
        }
        showPaired()
        checkConnection()
    }

    private fun showPaired() {
        connection.text = "Paired with ${baseUrl}"
        remotePanel.visibility = View.VISIBLE
    }

    private fun scanQr() {
        cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
    }

    private fun launchScanner() {
        try {
            val options = ScanOptions().apply {
                setPrompt("Scan the QR code shown by ProxiTune on Windows")
                setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                setOrientationLocked(false)
                setBeepEnabled(true)
            }
            barcodeLauncher.launch(options)
        } catch (error: Exception) {
            connection.text = "Could not open camera scanner: ${error.message ?: "unknown error"}"
        }
    }

    private fun pairFrom(contents: String) {
        try {
            val uri = Uri.parse(contents)
            val url = uri.getQueryParameter("url") ?: throw IllegalArgumentException("QR has no server URL")
            val newToken = uri.getQueryParameter("token") ?: throw IllegalArgumentException("QR has no token")
            baseUrl = url.trimEnd('/')
            token = newToken
            preferences.edit().putString("url", baseUrl).putString("token", token).apply()
            showPaired()
            status.text = "Pairing saved. Checking Windows…"
            checkConnection()
        } catch (error: Exception) {
            connection.text = "Could not read pairing QR: ${error.message}"
        }
    }

    private fun checkConnection() {
        request("/status", null) { ok, body ->
            runOnUiThread { connection.text = if (ok) "Connected to ProxiTune on Windows" else "Cannot reach Windows app: $body" }
        }
    }

    private fun sendZone(zone: String) {
        status.text = "Switching to $zone…"
        request("/zone", JSONObject().put("zone", zone).toString()) { ok, body ->
            runOnUiThread { status.text = if (ok) "Playing through $zone" else "Switch failed: $body" }
        }
    }

    private fun sendMedia(action: String) {
        status.text = "Sending media command…"
        request("/media", JSONObject().put("action", action).toString()) { ok, body ->
            runOnUiThread { status.text = if (ok) "Media command sent" else "Media command failed: $body" }
        }
    }

    private fun request(path: String, body: String?, callback: (Boolean, String) -> Unit) {
        val url = baseUrl
        val auth = token
        if (url.isNullOrBlank() || auth.isNullOrBlank()) {
            callback(false, "Not paired")
            return
        }
        executor.execute {
            try {
                val endpoint = Uri.parse("${url.trimEnd('/')}$path").buildUpon().appendQueryParameter("token", auth).build().toString()
                val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
                    requestMethod = if (body == null) "GET" else "POST"
                    connectTimeout = 4000
                    readTimeout = 6000
                    setRequestProperty("Content-Type", "application/json")
                    doInput = true
                    if (body != null) {
                        doOutput = true
                        outputStream.use { it.write(body.toByteArray()) }
                    }
                }
                val response = (if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream)
                    ?.bufferedReader()?.use { it.readText() } ?: ""
                callback(connection.responseCode in 200..299, response)
                connection.disconnect()
            } catch (error: Exception) {
                callback(false, error.message ?: "network error")
            }
        }
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }
}
