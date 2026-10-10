// Package monitoring reports errors to Sentry.
//
// Sentry is switched on only when SENTRY_DSN is set, which the pipeline does
// for staging and production. Local runs, Kind and previews send nothing.
// The release comes from the version baked into the image, the environment
// from runtime configuration, so one build reports correctly everywhere.
package monitoring

import (
	"time"

	"github.com/getsentry/sentry-go"

	"github.com/devwithvino/cicd_demo/services/api/internal/buildinfo"
	"github.com/devwithvino/cicd_demo/services/api/internal/config"
)

// Release is the Sentry release name shared by every Shipyard service.
func Release() string {
	return "shipyard@" + buildinfo.Version
}

// Init configures Sentry. It returns false, and does nothing, without a DSN.
func Init(cfg config.Config) (bool, error) {
	if cfg.SentryDSN == "" {
		return false, nil
	}
	err := sentry.Init(sentry.ClientOptions{
		Dsn:              cfg.SentryDSN,
		Environment:      cfg.Environment,
		Release:          Release(),
		AttachStacktrace: true,
		// The SDK defaults send no personal data such as IPs or cookies.
	})
	if err != nil {
		return false, err
	}
	sentry.ConfigureScope(func(scope *sentry.Scope) {
		scope.SetTag("service", "api")
		scope.SetTag("commit", buildinfo.Commit)
	})
	return true, nil
}

// Flush waits briefly for queued events before the process exits.
func Flush() {
	sentry.Flush(2 * time.Second)
}
