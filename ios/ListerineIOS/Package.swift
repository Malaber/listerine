// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ListerineIOS",
    platforms: [
        .iOS(.v16),
        .macOS(.v13)
    ],
    products: [
        .library(name: "ListerineCore", targets: ["ListerineCore"])
    ],
    targets: [
        .target(
            name: "ListerineCore",
            path: "Sources/ListerineCore"
        ),
        .testTarget(
            name: "ListerineCoreTests",
            dependencies: ["ListerineCore"],
            path: "Tests/ListerineCoreTests"
        )
    ]
)
