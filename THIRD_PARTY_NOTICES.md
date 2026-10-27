# Third-party notices

## Gradle Wrapper

The Gradle wrapper scripts and wrapper JAR are generated Gradle build tooling,
distributed under Apache License 2.0. Their original notices are retained.

- https://github.com/gradle/gradle
- https://www.apache.org/licenses/LICENSE-2.0

## Build and test dependencies

Android Gradle Plugin, the Android SDK, JUnit 4 and JSON-java are downloaded by
the build tools. JUnit and JSON-java are test-only and are not packaged into
the bridge APK. See their upstream license notices when redistributing them.

## Wallpaper images

Files under `wallpapers/nintendo/images/` are third-party visual assets owned by
Nintendo and/or the respective artists, not MIT-licensed project code. Per-image
source records and credits are in `wallpapers/nintendo/manifest.json`. Attribution
does not grant additional redistribution or commercial rights; consult source terms.

The bridge does not redistribute the vendor speech engine, vendor libraries,
vendor decompiled sources, media-player APKs, or speech-model files. Native
component names and message topic identifiers describe interoperability with
software already installed on an authorized device.
