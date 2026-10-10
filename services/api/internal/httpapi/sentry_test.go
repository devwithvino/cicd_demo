package httpapi

import (
	"net/http"
	"sync"
	"testing"

	"github.com/getsentry/sentry-go"

	"github.com/devwithvino/cicd_demo/services/api/internal/buildinfo"
)

func TestBrokenReleaseIsReportedToSentry(t *testing.T) {
	var (
		mu     sync.Mutex
		events []*sentry.Event
	)
	err := sentry.Init(sentry.ClientOptions{
		Dsn: "https://public@example.ingest.sentry.io/1",
		BeforeSend: func(event *sentry.Event, _ *sentry.EventHint) *sentry.Event {
			mu.Lock()
			events = append(events, event)
			mu.Unlock()
			return nil // record it, never send it
		},
	})
	if err != nil {
		t.Fatalf("sentry init: %v", err)
	}
	t.Cleanup(func() { _ = sentry.Init(sentry.ClientOptions{}) })

	buildinfo.BrokenRelease = "true"
	t.Cleanup(func() { buildinfo.BrokenRelease = "false" })

	rec := do(t, newTestServer(t, &fakeStore{}, ""), http.MethodPost, "/jobs", `{"payload":"x"}`)
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d, want 500", rec.Code)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(events) != 1 || len(events[0].Exception) == 0 {
		t.Fatalf("want one exception event, got %d events", len(events))
	}
	if got := events[0].Exception[0].Value; got != "job submission is broken in this release" {
		t.Fatalf("exception = %q", got)
	}
}
