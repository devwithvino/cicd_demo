package monitoring

import (
	"testing"

	"github.com/devwithvino/cicd_demo/services/api/internal/buildinfo"
	"github.com/devwithvino/cicd_demo/services/api/internal/config"
)

func TestInitIsANoOpWithoutDSN(t *testing.T) {
	enabled, err := Init(config.Config{Environment: "local"})
	if err != nil || enabled {
		t.Fatalf("enabled = %v, err = %v, want disabled without error", enabled, err)
	}
}

func TestInitWithDSN(t *testing.T) {
	enabled, err := Init(config.Config{Environment: "staging", SentryDSN: "https://public@example.ingest.sentry.io/1"})
	if err != nil || !enabled {
		t.Fatalf("enabled = %v, err = %v, want enabled", enabled, err)
	}
}

func TestReleaseUsesTheBakedVersion(t *testing.T) {
	buildinfo.Version = "1.2.3"
	t.Cleanup(func() { buildinfo.Version = "dev" })
	if got := Release(); got != "shipyard@1.2.3" {
		t.Fatalf("Release() = %q", got)
	}
}
