# Listerine iPhone app

This folder contains a starter SwiftUI iPhone client for Listerine plus a Swift package with automated tests for the app's core logic.

## Folder layout

- `Package.swift` builds the reusable `ListerineCore` module and its test suite
- `Sources/ListerineCore/` contains the backend URL persistence, passkey scaffolding, and authentication view model logic
- `App/` contains the SwiftUI application shell and the Apple passkey bridge for Xcode app targets
- `Tests/ListerineCoreTests/` contains high-coverage tests for the app's core behavior

## Run tests locally

```bash
.venv/bin/inv check-ios-e2e
```

Useful native iOS Invoke targets:

- `.venv/bin/inv install-xcodegen`
- `.venv/bin/inv check-ios-package`
- `.venv/bin/inv run-ios-e2e`
- `.venv/bin/inv check-ios-e2e`
- `.venv/bin/inv generate-ios-project`
- `.venv/bin/inv build-ios-simulator`
- `.venv/bin/inv check-ios-ci`

## Project setup in Xcode

1. Open Xcode 16 or newer on macOS.
2. Open `ios/ListerineIOS/ListerineApp.xcodeproj`.
3. Use the `Listerine` scheme to build and run the native app on an iPhone simulator or device.
4. Open `ios/ListerineIOS/Package.swift` in Xcode as needed to inspect or run the Swift package tests for `ListerineCore`.

## Included app flow

- configurable backend URL with `https://listerine.malaber.de` as the default suggestion
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
5. Launch from Xcode and verify:
   - backend can be changed in-app
   - passkey login succeeds for the selected backend
   - list switching works
   - adding/editing/checking/deleting items updates correctly
   - the device or simulator can satisfy the Apple passkey prompt

## Passkey login notes

- The native app now accepts the backend's current `/api/v1/auth/login/options` response shape directly, whether the WebAuthn options are top-level or nested under `publicKey`.
- The app relies on the `Set-Cookie` session from `/api/v1/auth/login/options` to complete `/api/v1/auth/login/verify`, so login tests should always use the same session between both requests.
- For local native passkey checks, use `localhost` as the browser-facing host and RP ID. `127.0.0.1` is not valid for WebAuthn passkey UX in Apple and Chromium clients.

## Shipping to the App Store

1. Join the Apple Developer Program and create an App ID for the iOS app.
2. In Xcode, configure the bundle identifier, signing team, app icon, launch assets, and display metadata.
3. Add privacy disclosures in App Store Connect, including whether account identifiers or diagnostics are collected.
4. If passkeys are used in production, verify the associated domains and WebAuthn relying party configuration you will use for the final backend.
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
