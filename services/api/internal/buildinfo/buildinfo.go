// Package buildinfo holds metadata baked into the binary at build time.
//
// Values are injected with -ldflags so the same image always reports the
// same version and commit, no matter which environment runs it.
package buildinfo

import "time"

var (
	// Version is the semantic version of the release.
	Version = "dev"
	// Commit is the full git commit SHA the image was built from.
	Commit = "unknown"
	// BuildTime is the RFC 3339 timestamp of the build.
	BuildTime = "unknown"
	// BrokenRelease turns on the deliberate failure used by the rollback demo.
	// It is only ever set to "true" by the demo-failure workflow.
	BrokenRelease = "false"
)

// StartedAt records when the process started, for uptime reporting.
var StartedAt = time.Now().UTC()

// IsBroken reports whether this build is the deliberately broken demo release.
func IsBroken() bool {
	return BrokenRelease == "true"
}
