// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "PlaniniIOS",
    platforms: [
        .iOS(.v16),
        .watchOS(.v10),
        .macOS(.v13)
    ],
    products: [
        .library(name: "PlaniniCore", targets: ["PlaniniCore"])
    ],
    targets: [
        .target(
            name: "PlaniniCore",
            path: "Sources/PlaniniCore"
        ),
        .testTarget(
            name: "PlaniniCoreTests",
            dependencies: ["PlaniniCore"],
            path: "Tests/PlaniniCoreTests"
        )
    ]
)
