// Gradle init-script: temporarily override the `:TPipe-TraceServer:run`
// task's mainClass without editing build.gradle.kts.
//
// Usage:
//   1. Copy this file somewhere outside the repo (e.g. /tmp/hermes-verify-*/).
//   2. Edit the `mainClass.set(...)` line below to point at the smoke
//      main you want to run.
//   3. Invoke:
//        ./gradlew --init-script /path/to/override.init.gradle.kts \
//                 :TPipe-TraceServer:run --no-daemon
//
// Background: the `application` Gradle plugin reads `mainClass` from the
// `application { }` extension at tasksEvaluated; the `-PmainClass=...`
// property does NOT override it. projectsEvaluated is the right hook
// because the application plugin's JavaExec task has been registered
// by then but has not yet been configured for execution.

gradle.projectsEvaluated {
    rootProject.allprojects {
        if (name == "TPipe-TraceServer") {
            tasks.named<JavaExec>("run") {
                mainClass.set("com.TTT.TraceServer.TraceServerSmokeMainKt")
            }
        }
    }
}
