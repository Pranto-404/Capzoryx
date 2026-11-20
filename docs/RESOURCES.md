# Free service configuration

| Use | Resource | Configuration |
| --- | --- | --- |
| Website | Vercel Capzoryx, branch main | Project root directory `web`. The public website is https://capzoryx.vercel.app. |
| Installable app | Vercel capzoryx-app, branch v2 | Repository root. The app is https://capzoryx-app.vercel.app. Android signing and installation instructions are below. |
| Live API | Render capzoryx-staging-api | Despite its historical service name, this service and its Turso database serve the live website and app. Synthetic tests run locally or against an isolated QA origin. |
| QA | Vercel capzoryx-qa and Render capzoryx-qa-api | Dedicated API on the free Singapore instance. Supply its own Turso URL/token and independent signing key. Verify the deployed commit and libSQL readiness before starting its 24-hour soak. |
| Model evaluation | Local CPU | The browser parser and deterministic finance engine work without external keys. Train the optional tagger locally. Independently written samples can be collected at /field-kit/index.html. |
| Optional QLoRA | Free CUDA notebook session | Run ml/hisab_lm/train.ipynb only on a free CUDA allocation. Keep adapters and model credentials outside the public repository. |
| Optional notifications | Cloudflare Workers Free and GitHub Actions | Set separate staging and live tick secrets using the deployment instructions in infra/notification-tick. New alerts are readable in Activity. |
| Optional delivery | VAPID, Firebase or Telegram | Configure only a channel chosen by the owner. Device and recipient consent are required before delivery. |

The hosted app does not require a paid AI key, paid SMS, a Student Pack, or a Play Store account. Student benefits and any free GPU quota are personal account entitlements. The owner can claim them through the relevant provider if eligible. Retain the free plan when quotas run out.

## Isolated staging

1. Create a free database named `capzoryx-qa` in the owner's Turso organization. In its dashboard, copy its own libSQL URL and create a token scoped to that database.
2. Put the values in the QA Render service as `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`. Save the environment and deploy branch v2. Keep the existing website's secrets in its own service.
3. Use the QA frontend to check `/api/health` for the candidate commit and `/api/ready` for `libsql`. The QA scheduler, API, and test workspace must all use these isolated resources.
4. Run a full 24-hour soak with synthetic records, verify the notification schedule and perform the rollback drill before claiming production qualification.

# Android build and release

The package ID is `com.capzoryx.copilot`. Debug builds add `.debug`, so a test installation can coexist with a signed release. The WebView loads bundled files at `https://app.capzoryx.local`. API calls go to the Capzoryx Vercel website. Public passport links and invitations also use the website origin.

## Build a debug APK

Install JDK 21, Node 22, Gradle 8.14.3 and the Android SDK command-line tools. Set `ANDROID_HOME` to the SDK directory. From the repository root run

```sh
sdkmanager 'platforms;android-36' 'build-tools;35.0.0' 'build-tools;36.0.0' 'platform-tools'
npm ci --prefix web
npm run build:native --prefix web
gradle -p web/android :app:assembleDebug
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify web/android/app/build/outputs/apk/debug/app-debug.apk
adb install -r web/android/app/build/outputs/apk/debug/app-debug.apk
```

For an emulator or a device with USB debugging enabled run `gradle -p web/android :app:connectedDebugAndroidTest`. The Android workflow also opens the bundled app on an Android emulator with data and Wi-Fi disabled. The first visit can display the public interface or the capture screen offline. Signing in to an account requires network access.

## Owner-controlled release signing

Keep a private backup of the release keystore and its password. For the first sideloaded release, use a permanent key created by the app owner. Reuse the same key when releasing app updates.

```sh
keytool -genkeypair -keystore capzoryx-release.jks -storetype PKCS12 -alias capzoryx -keyalg RSA -keysize 3072 -validity 10000
keytool -list -v -keystore capzoryx-release.jks -alias capzoryx
```

Run these commands in a private directory outside the repository. In GitHub Settings → Environments, create `android-release` and allow deployments from `v2`. Add these secrets and the public certificate fingerprint. Enter passwords in GitHub or at an interactive prompt.

| Name | Value |
| --- | --- |
| `CAPZORYX_ANDROID_KEYSTORE_BASE64` | Base64-encoded keystore, uploaded directly |
| `CAPZORYX_ANDROID_KEY_ALIAS` | Signing alias, normally `capzoryx` |
| `CAPZORYX_ANDROID_STORE_PASSWORD` | Keystore password |
| `CAPZORYX_ANDROID_KEY_PASSWORD` | Key password, the same as the store password for PKCS12 |
| `CAPZORYX_ANDROID_CERT_SHA256` (variable) | The release certificate's colon-separated SHA-256 fingerprint |

```sh
base64 -w0 capzoryx-release.jks | gh secret set CAPZORYX_ANDROID_KEYSTORE_BASE64 --env android-release --repo Pranto-404/Capzoryx
gh workflow run android.yml --ref v2 -f release=true --repo Pranto-404/Capzoryx
```

Download the verified APK, AAB and Digital Asset Links file from the successful workflow artifact. Set the same **public fingerprint** as the `CAPZORYX_ANDROID_CERT_SHA256` production build variable in the website project and redeploy. The website build emits `/.well-known/assetlinks.json`. Without a published release fingerprint it emits an empty list of app associations. For a future Play Store release, the website must trust the store's **app signing certificate** when it differs from the sideload signing key.

On a physical Android 12 or newer device, install the release APK. Run `adb shell pm verify-app-links --re-verify com.capzoryx.copilot`, wait for Android's verifier, then check `adb shell pm get-app-links com.capzoryx.copilot`. Confirm a valid public passport or workspace invitation opens in the app.

## Native dependencies

| Package | Version | Purpose |
| --- | --- | --- |
| @capacitor/core, @capacitor/cli, @capacitor/android | 8.6.2 | Android bridge, packaging and runtime |
| @capacitor/app | 8.1.2 | Receive verified links |
| @capacitor/camera | 8.2.6 | Camera access for user-initiated capture |
| @capacitor/local-notifications | 8.3.1 | Local notification interface |
| @capacitor/share | 8.0.3 | Android share sheet |
| @capacitor-firebase/messaging | 8.6.0 | FCM integration |
| @capgo/capacitor-share-target | 8.0.68 | Receive bounded text shares |
| @aparajita/capacitor-biometric-auth | 10.0.0 | Android biometric prompt |
| @aparajita/capacitor-secure-storage | 8.0.1 | Encrypted session storage backed by Android Keystore |

Plugin versions are pinned in the npm lockfile. FCM auto-initialization and analytics collection default to disabled. A working push delivery setup needs the owner's Firebase Android configuration, server delivery credentials, explicit notification permission and a registered notification device. Tokens for signing in are stored together in the native encrypted store. Public website and PWA sessions continue to use HttpOnly cookies.
