import Foundation

public struct PlaniniLocalizationCatalog {
    public let defaultLocale: String
    private let catalogs: [String: [String: Any]]

    public init(defaultLocale: String = "en", catalogs: [String: [String: Any]]) {
        self.defaultLocale = defaultLocale
        self.catalogs = catalogs
    }

    public var availableLocales: [String] {
        catalogs.keys.sorted()
    }

    public func effectiveLocale(
        preferredLocales: [String] = Locale.preferredLanguages,
        overrideLocale: String? = nil
    ) -> String {
        if let locale = normalizedAvailableLocale(overrideLocale) {
            return locale
        }

        for preferredLocale in preferredLocales {
            if let locale = normalizedAvailableLocale(preferredLocale) {
                return locale
            }
        }

        return normalizedAvailableLocale(defaultLocale) ?? defaultLocale
    }

    public func translate(
        locale: String,
        key: String,
        params: [String: CustomStringConvertible] = [:]
    ) -> String {
        let locale = normalizedAvailableLocale(locale) ?? defaultLocale
        let value = stringValue(for: key, locale: locale)
            ?? stringValue(for: key, locale: defaultLocale)
            ?? key
        guard params.isEmpty == false else { return value }
        return params.reduce(value) { text, entry in
            text.replacingOccurrences(of: "{\(entry.key)}", with: entry.value.description)
        }
    }

    public func normalizedAvailableLocale(_ rawValue: String?) -> String? {
        guard let rawValue else { return nil }
        let normalized = rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "_", with: "-")
            .lowercased()
        guard normalized.isEmpty == false else { return nil }
        if catalogs[normalized] != nil {
            return normalized
        }
        if let languageCode = normalized.split(separator: "-").first.map(String.init),
           catalogs[languageCode] != nil
        {
            return languageCode
        }
        return nil
    }

    private func stringValue(for key: String, locale: String) -> String? {
        guard let catalog = catalogs[locale] else { return nil }
        var current: Any = catalog
        for part in key.split(separator: ".").map(String.init) {
            guard
                let dictionary = current as? [String: Any],
                let value = dictionary[part]
            else {
                return nil
            }
            current = value
        }
        return current as? String
    }
}
