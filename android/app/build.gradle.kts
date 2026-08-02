plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.namans12.proxitune"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.namans12.proxitune"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
}

kotlin { jvmToolchain(21) }

dependencies {
    implementation("androidx.activity:activity-ktx:1.9.2")
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")
}
