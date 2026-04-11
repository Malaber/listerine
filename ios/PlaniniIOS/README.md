# Planini iPhone app

This folder contains a starter SwiftUI iPhone client for Planini plus a Swift package with automated tests for the app's core logic.

## Folder layout

- `Package.swift` builds the reusable `PlaniniCore` module and its test suite
- `Sources/PlaniniCore/` contains the backend URL persistence, passkey scaffolding, and authentication view model logic
- `App/` contains the SwiftUI application shell and the Apple passkey bridge for Xcode app targets
- `Tests/PlaniniCoreTests/` contains high-coverage tests for the app's core behavior

## Run tests locally

```bash
.venv/bin/inv check-ios-e2e
```

Useful native iOS Invoke targets:

- `.venv/bin/inv install-xcodegen`
- `.venv/bin/inv configure-ios-app --backend-url=https://your.domain --bundle-id=com.example.yourapp`
- `.venv/bin/inv start-ios-backend --backend-url=https://your.domain`
- `.venv/bin/inv check-ios-package`
- `.venv/bin/inv run-ios-e2e`
- `.venv/bin/inv check-ios-e2e`
- `.venv/bin/inv generate-ios-project`
- `.venv/bin/inv build-ios-simulator`
- `.venv/bin/inv run-ios-simulators-fresh`
- `.venv/bin/inv check-ios-ci`

### Common configure commands

Use the same `configure-ios-app` target in two common ways:

1. Normal live app build against the main hosted backend:
```bash
.venv/bin/inv configure-ios-app \
  --backend-url=https://planini.malaber.de \
  --bundle-id=de.malaber.planini \
  --development-team=VWKG94374J
```

2. Review-host build against one PR app while still using the shared review passkey host:
```bash
.venv/bin/inv configure-ios-app \
  --backend-url=https://pr-49.pr.planini.malaber.de \
  --passkey-domain=pr.planini.malaber.de \
  --bundle-id=de.malaber.planini \
  --development-team=VWKG94374J
```

The first form is the normal production-style configuration. The second form is
for native review testing, where the app talks to a specific PR deployment but
Apple passkeys still validate against the shared review host.

## Project setup in Xcode

1. Open Xcode 16 or newer on macOS.
2. Open `ios/PlaniniIOS/PlaniniApp.xcodeproj`.
3. Use the `Planini` scheme to build and run the native app on an iPhone simulator or device.
4. Open `ios/PlaniniIOS/Package.swift` in Xcode as needed to inspect or run the Swift package tests for `PlaniniCore`.

## Included app flow

- build-time configured backend URL with `https://planini.malaber.de` as the default
- passkey login against `/api/v1/auth/login/options` and `/api/v1/auth/login/verify`
- bearer-token authenticated loading of households, lists, and list items
- list switching plus add, remove, check/uncheck, and edit item details
- liquid-glass inspired SwiftUI styling using material cards and gradients

## Local testing workflow

1. **Swift package checks (Linux/macOS):**
   ```bash
   .venv/bin/inv check-ios-package
   ```
2. **Live backend integration checks with the seeded passkey fixture (macOS):**
   ```bash
   .venv/bin/inv check-ios-e2e
   ```
   This Invoke target:
   - starts the FastAPI backend with `app/fixtures/review_seed_e2e.json`
   - keeps the backend session cookie for `/auth/login/options` and `/auth/login/verify`
   - signs a real WebAuthn assertion from the seeded private key fixture
   - verifies passkey login, list loading, add/edit/check/uncheck/delete item flows
3. **Generate the Xcode project if you need to regenerate it (macOS):**
   ```bash
   .venv/bin/inv generate-ios-project
   ```
4. **Build and run in Simulator (macOS):**
   ```bash
   .venv/bin/inv build-ios-simulator
   ```
5. **Reinstall and launch both paired simulators from scratch (macOS):**
   ```bash
   .venv/bin/inv run-ios-simulators-fresh
   ```
   This target:
   - boots the configured iPhone and Apple Watch simulators
   - uninstalls old app copies from both simulators
   - deletes a dedicated derived-data folder
   - rebuilds the app from scratch
   - installs the iPhone app and watch app
   - launches the iPhone app with the local backend/bootstrap env vars
   - launches the watch app after the iPhone app starts
6. Launch from Xcode and verify:
   - the configured backend matches the build settings you generated the app with
   - passkey login succeeds for the selected backend
   - list switching works
   - adding/editing/checking/deleting items updates correctly
   - the device or simulator can satisfy the Apple passkey prompt

## Self-hosted builds

Use Invoke to stamp the app with your backend domain and bundle identifier before building:

```bash
.venv/bin/inv configure-ios-app \
  --backend-url=https://shopping.example.com \
  --bundle-id=com.example.shopping \
  --development-team=YOURTEAMID
```

That task updates:
- the iOS app's embedded backend URL
- the associated-domain entitlement for `webcredentials:<your host>`
- the generated Xcode project

The backend URL is no longer edited inside the app.

To start a local backend with a matching WebAuthn RP ID for that build:

```bash
.venv/bin/inv start-ios-backend --backend-url=https://shopping.example.com
```

That derives `WEBAUTHN_RP_ID` from the configured backend host automatically.

## Passkey login notes

- The native app now accepts the backend's current `/api/v1/auth/login/options` response shape directly, whether the WebAuthn options are top-level or nested under `publicKey`.
- The app relies on the `Set-Cookie` session from `/api/v1/auth/login/options` to complete `/api/v1/auth/login/verify`, so login tests should always use the same session between both requests.
- For local native passkey checks, use `localhost` as the browser-facing host and RP ID. `127.0.0.1` is not valid for WebAuthn passkey UX in Apple and Chromium clients.
- The app target now includes the Associated Domains entitlement for `webcredentials:planini.malaber.de`.
- Production passkey login still requires a real Apple team ID and bundle identifier that match the `appID` entries served by `https://planini.malaber.de/.well-known/apple-app-site-association`.
- A locally signed placeholder app such as `FAKETEAMID.com.example.planini` will be rejected by `AuthenticationServices`, even if the backend URL and RP ID are otherwise correct.
- Self-hosted builds work when the builder signs the app themselves and uses `configure-ios-app` so the bundle ID, associated domain, and backend host all match.
- An App Store build cannot support arbitrary self-hosted passkey domains at runtime, because Apple Associated Domains are static entitlements.

## Passkey deployment checklist

The app and backend now have a strict deployment contract for native Apple passkeys. Both sides must be configured together.

### App build requirements

1. Run `configure-ios-app` with the final backend URL and bundle identifier for the build you will sign:
   ```bash
   .venv/bin/inv configure-ios-app \
     --backend-url=https://shopping.example.com \
     --bundle-id=com.example.shopping \
     --development-team=YOURTEAMID
   ```
2. Sign the app with the Apple Developer team that will ship the build.
3. Confirm the generated entitlement includes `webcredentials:shopping.example.com`.
4. Remember that the final Apple app identifier is `TEAM_ID.bundle_id`, for example `ABCD123456.com.example.shopping`.

### Backend deployment requirements

1. Serve the backend over HTTPS on the same hostname you embedded into the app.
2. Set `APP_BASE_URL` to that public HTTPS origin.
3. Set `WEBAUTHN_RP_ID` to that hostname. `start-ios-backend` derives it automatically for local runs, but production deployments still need to set it explicitly.
4. Set `WEBCREDENTIALS_APPS` to the signed Apple app ID.
5. The backend now serves an Apple App Site Association file from that config at:
   - `https://shopping.example.com/.well-known/apple-app-site-association`
6. The file must include the signed app identifier under `webcredentials.apps`, for example:
   ```json
   {
     "webcredentials": {
       "apps": [
         "ABCD123456.com.example.shopping"
       ]
     }
   }
   ```
7. Keep the host in all four places identical:
   - the app's embedded backend URL
   - the `webcredentials:<host>` entitlement
   - `APP_BASE_URL`
   - the backend's `WEBAUTHN_RP_ID`

If any of those values drift apart, the simulator or device will fail passkey login before the app can complete `/api/v1/auth/login/verify`.

### Review deployment note

Review deployments can intentionally split the app host from the passkey host:

- app backend URL: `https://pr-<PR>.pr.planini.malaber.de`
- passkey entitlement and RP ID: `pr.planini.malaber.de`

That shared-review setup only works if `pr.planini.malaber.de` itself serves
the Apple App Site Association payload for the signed app ID. It is not enough
for only the individual `pr-<PR>` app host to serve the AASA response.

## Shipping to the App Store

1. Join the Apple Developer Program and create an App ID for the iOS app.
2. In Xcode, configure the bundle identifier, signing team, app icon, launch assets, and display metadata.
3. Add privacy disclosures in App Store Connect, including whether account identifiers or diagnostics are collected.
4. If passkeys are used in production, verify the associated domains and WebAuthn relying party configuration you will use for the final backend.
   This includes:
   - setting the final Apple Developer team and bundle identifier
   - adding the matching `webcredentials:` domain entitlement to the app
   - serving an Apple App Site Association file for that exact app identifier on the backend domain
   - setting `WEBAUTHN_RP_ID` on the backend to the same hostname the app uses
5. Test on physical devices, especially sign-in flows, keyboard behavior, and network error handling.
6. Archive the app in Xcode, validate it, and upload it through Organizer.
7. In App Store Connect, create the app record, complete screenshots, pricing, age rating, and submission notes.
8. Submit for App Review and be ready to provide a demo account or backend test environment if Apple asks for one.


## GitHub Actions automation

Two workflows now automate most of the iOS delivery path:

- `.github/workflows/ci.yml` runs the Linux Swift package tests in parallel with the Python checks.
- `.github/workflows/ios-build-and-testflight.yml` bootstraps the backend dependencies on GitHub-hosted macOS runners, runs `inv check-ios-ci`, and optionally archives/exports/uploads a signed build to TestFlight.

### Secrets needed for TestFlight uploads

Set these GitHub Actions secrets before dispatching the TestFlight upload workflow:

- `APPLE_TEAM_ID`
- `IOS_BUNDLE_IDENTIFIER`
- `KEYCHAIN_PASSWORD`
- `BUILD_CERTIFICATE_BASE64`
- `P12_PASSWORD`
- `BUILD_PROVISION_PROFILE_BASE64`
- `BUILD_PROVISION_PROFILE_NAME`
- `APP_STORE_CONNECT_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`
- `APP_STORE_CONNECT_PRIVATE_KEY`

### How to use the workflow

1. Push the branch to GitHub so the `iOS Build and TestFlight` workflow appears.
2. Run the workflow once with `upload_to_testflight = false` to verify project generation and simulator builds.
3. Add the required signing and App Store Connect secrets.
4. Re-run it with `upload_to_testflight = true` to archive, export, and upload the IPA to TestFlight.
