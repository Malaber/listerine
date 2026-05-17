import Foundation
import Testing

@testable import PlaniniCore

struct PlaniniLinkTests {
    @Test func parsesAllowedPlaniniWebLinks() throws {
        let listID = try #require(UUID(uuidString: "11111111-2222-3333-4444-555555555555"))
        let allowedHosts: Set<String> = ["planini.top"]

        #expect(
            PlaniniLinkParser.parse(
                "https://planini.top/lists/\(listID.uuidString)?from=share",
                allowedWebHosts: allowedHosts
            ) == .list(id: listID)
        )
        #expect(
            PlaniniLinkParser.parse(
                "https://planini.top/invite/invite-token_123#join",
                allowedWebHosts: allowedHosts
            ) == .invite(token: "invite-token_123")
        )
        #expect(
            PlaniniLinkParser.parse(
                "https://planini.top/passkey-add/add-token.123",
                allowedWebHosts: allowedHosts
            ) == .passkeyAdd(token: "add-token.123")
        )
    }

    @Test func rejectsUntrustedWebHostsForInviteAndListLinks() {
        #expect(
            PlaniniLinkParser.parse(
                "https://evil.example/invite/token",
                allowedWebHosts: ["planini.top"]
            ) == nil
        )
        #expect(
            PlaniniLinkParser.parse(
                "https://evil.example/lists/11111111-2222-3333-4444-555555555555",
                allowedWebHosts: ["planini.top"]
            ) == nil
        )
    }

    @Test func parsesPlaniniSchemeLinksForSimulatorAutomation() {
        let listID = UUID()

        #expect(PlaniniLinkParser.parse("planini://invite/token-1") == .invite(token: "token-1"))
        #expect(PlaniniLinkParser.parse("planini://lists/\(listID.uuidString)") == .list(id: listID))
    }

    @Test func preservesExistingPasskeyAddInputs() {
        #expect(PlaniniLinkParser.passkeyAddToken(from: "raw-token_1") == "raw-token_1")
        #expect(
            PlaniniLinkParser.passkeyAddToken(
                from: "https://planini.top/passkey-add/token-2?unused=1"
            ) == "token-2"
        )
        #expect(PlaniniLinkParser.passkeyAddToken(from: "passkey-add://token-3") == "token-3")
        #expect(PlaniniLinkParser.passkeyAddToken(from: "bad token") == nil)
    }
}
