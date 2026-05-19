import Foundation
import PlaniniCore

@MainActor
final class AppLocalization: ObservableObject {
    static let systemPreferenceID = "system"

    private static let languageOverrideKey = "planini.languageOverride"
    nonisolated private static let defaultCatalogs: [String: [String: Any]] = [
        "en": [:],
    ]

    private let catalog: PlaniniLocalizationCatalog
    private let userDefaults: UserDefaults
    private let processInfo: ProcessInfo
    private let preferredLocales: () -> [String]

    @Published private(set) var overrideLocale: String?

    init(
        catalog: PlaniniLocalizationCatalog = AppLocalization.loadBundledCatalog(),
        userDefaults: UserDefaults = .standard,
        processInfo: ProcessInfo = .processInfo,
        preferredLocales: @escaping () -> [String] = { Locale.preferredLanguages }
    ) {
        self.catalog = catalog
        self.userDefaults = userDefaults
        self.processInfo = processInfo
        self.preferredLocales = preferredLocales

        if processInfo.environment["PLANINI_UI_TEST_MODE"] == "1" {
            overrideLocale = catalog.normalizedAvailableLocale(
                processInfo.environment["PLANINI_UI_TEST_LANGUAGE"]
            )
        } else {
            overrideLocale = catalog.normalizedAvailableLocale(
                userDefaults.string(forKey: Self.languageOverrideKey)
            )
        }
    }

    var effectiveLocale: String {
        catalog.effectiveLocale(
            preferredLocales: preferredLocales(),
            overrideLocale: overrideLocale
        )
    }

    var preferenceID: String {
        overrideLocale ?? Self.systemPreferenceID
    }

    var availableLocaleIDs: [String] {
        catalog.availableLocales
    }

    func setPreference(id: String) {
        let normalized = catalog.normalizedAvailableLocale(id)
        overrideLocale = normalized
        if let normalized {
            userDefaults.set(normalized, forKey: Self.languageOverrideKey)
        } else {
            userDefaults.removeObject(forKey: Self.languageOverrideKey)
        }
    }

    func t(_ key: String, _ params: [String: CustomStringConvertible] = [:]) -> String {
        catalog.translate(locale: effectiveLocale, key: key, params: params)
    }

    func localizedLanguageName(for locale: String) -> String {
        switch locale {
        case "de":
            return t("ios.language.german")
        case "en":
            return t("ios.language.english")
        default:
            return locale
        }
    }

    func languagePreferenceTitle(for id: String) -> String {
        if id == Self.systemPreferenceID {
            return t("ios.settings.language_system_automatic")
        }
        return localizedLanguageName(for: id)
    }

    func currentLanguageSummary() -> String {
        if let overrideLocale {
            return localizedLanguageName(for: overrideLocale)
        }
        return t(
            "ios.settings.language_system_summary",
            ["language": localizedLanguageName(for: effectiveLocale)]
        )
    }

    nonisolated private static func loadBundledCatalog(bundle: Bundle = .main) -> PlaniniLocalizationCatalog {
        var catalogs: [String: [String: Any]] = [:]
        for locale in ["en", "de"] {
            guard let url = localeCatalogURL(locale: locale, bundle: bundle),
                  let data = try? Data(contentsOf: url),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else {
                continue
            }
            catalogs[locale] = json
        }
        return PlaniniLocalizationCatalog(
            catalogs: catalogs.isEmpty ? defaultCatalogs : catalogs
        )
    }

    nonisolated private static func localeCatalogURL(locale: String, bundle: Bundle) -> URL? {
        if let url = bundle.url(forResource: locale, withExtension: "json", subdirectory: "locales") {
            return url
        }
        return bundle.url(forResource: locale, withExtension: "json")
    }
}
