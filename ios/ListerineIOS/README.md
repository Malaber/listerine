# Listerine iPhone app

This folder contains a starter SwiftUI iPhone client for Listerine plus a Swift package with automated tests for the app's core logic.

## Folder layout

- `Package.swift` builds the reusable `ListerineCore` module and its test suite
- `Sources/ListerineCore/` contains the backend URL persistence, passkey scaffolding, and authentication view model logic
- `App/` contains the SwiftUI application shell and the Apple passkey bridge for Xcode app targets
- `Tests/ListerineCoreTests/` contains high-coverage tests for the app's core behavior

## Run tests locally

```bash
cd ios/ListerineIOS
./Scripts/check_coverage.sh
```

## Project setup in Xcode

1. Open Xcode 16 or newer on macOS.
2. Open `ios/ListerineIOS/Package.swift` in Xcode to inspect or run the tests for `ListerineCore`.
3. Create a new **App** project in Xcode named `Listerine` and add `ListerineCore` as a local package dependency from this folder.
4. Copy the files from `ios/ListerineIOS/App/` into that Xcode app target.
5. Set the deployment target to **iOS 16.0** or newer.
6. Run the app on an iPhone simulator or device.

## Included app flow

- first-launch backend URL entry and local persistence
- passkey sign-up button
- passkey login button
- placeholder passkey request generation using `AuthenticationServices` on Apple platforms
- integration notes for connecting to the future backend passkey endpoints

## Backend work needed to finish passkey auth

The app is intentionally ready only up to local passkey request creation. To complete the feature, the backend will need endpoints that:

1. return a WebAuthn registration challenge for sign-up
2. verify the registration response and create the account
3. return a WebAuthn assertion challenge for login
4. verify the assertion response and establish an authenticated session or token
5. expose the relying party ID and any environment-specific passkey metadata the app should trust

When those routes exist, update `ApplePasskeyClient.swift` to submit server-provided challenges and send the completed registration/assertion payload back to the API.

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
- `.github/workflows/ios-build-and-testflight.yml` can generate the Xcode project on GitHub-hosted macOS runners, build the app for the iOS simulator, and optionally archive/export/upload a signed build to TestFlight.

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
