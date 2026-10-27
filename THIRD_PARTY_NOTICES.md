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

The bridge does not redistribute the vendor speech engine, vendor libraries,
vendor decompiled sources, media-player APKs, or speech-model files. Native
component names and message topic identifiers describe interoperability with
software already installed on an authorized device.
