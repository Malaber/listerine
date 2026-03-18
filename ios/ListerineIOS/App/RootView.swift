import ListerineCore
import SwiftUI

struct RootView: View {
    @EnvironmentObject private var authViewModel: AuthViewModel

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("https://api.example.com", text: $authViewModel.backendURLInput)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button("Save Backend URL") {
                        authViewModel.saveBackendURL()
                    }

                    if authViewModel.configuration.hasBackendURL {
                        Button("Clear Backend URL", role: .destructive) {
                            authViewModel.resetBackendURL()
                        }
                    }

                    LabeledContent("Current backend", value: authViewModel.backendURLDescription)
                        .font(.footnote)
                }

                Section("Account") {
                    TextField("Email or username", text: $authViewModel.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Button {
                        Task {
                            await authViewModel.performPasskey(.signUp)
                        }
                    } label: {
                        authButtonLabel(title: "Sign Up with Passkey")
                    }
                    .disabled(authViewModel.isPerformingPasskeyRequest)

                    Button {
                        Task {
                            await authViewModel.performPasskey(.logIn)
                        }
                    } label: {
                        authButtonLabel(title: "Log In with Passkey")
                    }
                    .disabled(authViewModel.isPerformingPasskeyRequest)
                }

                Section("Integration Notes") {
                    Text("This app currently validates the backend URL, prepares passkey registration/assertion requests, and stores the selected environment on-device.")
                    Text("When your backend passkey routes are ready, connect the request results to your API and replace the placeholder challenge with server-provided values.")
                }

                if authViewModel.latestStatusMessage.isEmpty == false {
                    Section("Status") {
                        Text(authViewModel.latestStatusMessage)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Listerine")
            .alert(
                "Unable to continue",
                isPresented: Binding(
                    get: { authViewModel.errorMessage != nil },
                    set: { newValue in
                        if newValue == false {
                            authViewModel.errorMessage = nil
                        }
                    }
                ),
                actions: {
                    Button("OK", role: .cancel) {
                        authViewModel.errorMessage = nil
                    }
                },
                message: {
                    Text(authViewModel.errorMessage ?? "Unknown error")
                }
            )
        }
    }

    @ViewBuilder
    private func authButtonLabel(title: String) -> some View {
        if authViewModel.isPerformingPasskeyRequest {
            HStack {
                ProgressView()
                Text("Working…")
            }
        } else {
            Text(title)
        }
    }
}

#Preview {
    RootView()
        .environmentObject(
            AuthViewModel(
                urlStore: BackendURLStore(),
                passkeyService: PasskeyAuthService(client: ApplePasskeyClient())
            )
        )
}
