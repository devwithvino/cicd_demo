package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/devwithvino/cicd_demo/services/api/internal/buildinfo"
	"github.com/devwithvino/cicd_demo/services/api/internal/config"
	"github.com/devwithvino/cicd_demo/services/api/internal/jobs"
)

type fakeStore struct {
	pingErr error
	created []jobs.Job
}

func (f *fakeStore) Ping(context.Context) error { return f.pingErr }

func (f *fakeStore) Create(_ context.Context, payload, by string) (jobs.Job, error) {
	job := jobs.Job{ID: "abc123", Payload: payload, Status: jobs.StatusQueued, SubmittedBy: by}
	f.created = append(f.created, job)
	return job, nil
}

func (f *fakeStore) Get(_ context.Context, id string) (jobs.Job, error) {
	for _, job := range f.created {
		if job.ID == id {
			return job, nil
		}
	}
	return jobs.Job{}, jobs.ErrNotFound
}

func (f *fakeStore) Recent(context.Context) ([]jobs.Job, error) { return f.created, nil }

func (f *fakeStore) QueueDepth(context.Context) (int64, error) { return int64(len(f.created)), nil }

func newTestServer(t *testing.T, store JobStore, workerURL string) http.Handler {
	t.Helper()
	cfg := config.Config{Environment: "test", WorkerURL: workerURL, RepoURL: "https://example.com/repo"}
	return New(cfg, store, slog.New(slog.NewTextHandler(io.Discard, nil))).Handler()
}

func do(t *testing.T, h http.Handler, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestHealthz(t *testing.T) {
	rec := do(t, newTestServer(t, &fakeStore{}, ""), http.MethodGet, "/healthz", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d", rec.Code)
	}
	if rec.Header().Get("X-Request-ID") == "" {
		t.Fatal("missing X-Request-ID header")
	}
}

func TestReadyzReflectsKeyValue(t *testing.T) {
	h := newTestServer(t, &fakeStore{pingErr: errors.New("down")}, "")
	if rec := do(t, h, http.MethodGet, "/readyz", ""); rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503", rec.Code)
	}
	h = newTestServer(t, &fakeStore{}, "")
	if rec := do(t, h, http.MethodGet, "/readyz", ""); rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", rec.Code)
	}
}

func TestVersionReportsBuildAndEnvironment(t *testing.T) {
	buildinfo.Version, buildinfo.Commit = "1.2.3", "deadbeef"
	t.Cleanup(func() { buildinfo.Version, buildinfo.Commit = "dev", "unknown" })

	rec := do(t, newTestServer(t, &fakeStore{}, ""), http.MethodGet, "/version", "")
	var info VersionInfo
	if err := json.Unmarshal(rec.Body.Bytes(), &info); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if info.Version != "1.2.3" || info.Commit != "deadbeef" || info.Environment != "test" {
		t.Fatalf("unexpected version info: %+v", info)
	}
	if info.CommitURL != "https://example.com/repo/commit/deadbeef" {
		t.Fatalf("commit url = %q", info.CommitURL)
	}
}

func TestCreateAndGetJob(t *testing.T) {
	store := &fakeStore{}
	h := newTestServer(t, store, "")

	rec := do(t, h, http.MethodPost, "/jobs", `{"payload":"  resize image  "}`)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("create status = %d, body = %s", rec.Code, rec.Body)
	}
	if store.created[0].Payload != "resize image" {
		t.Fatalf("payload not trimmed: %q", store.created[0].Payload)
	}

	if rec := do(t, h, http.MethodGet, "/jobs/abc123", ""); rec.Code != http.StatusOK {
		t.Fatalf("get status = %d", rec.Code)
	}
	if rec := do(t, h, http.MethodGet, "/jobs/nope", ""); rec.Code != http.StatusNotFound {
		t.Fatalf("missing job status = %d", rec.Code)
	}
}

func TestCreateJobValidation(t *testing.T) {
	h := newTestServer(t, &fakeStore{}, "")
	for _, body := range []string{"", "not json", `{"payload":"   "}`} {
		if rec := do(t, h, http.MethodPost, "/jobs", body); rec.Code != http.StatusBadRequest {
			t.Errorf("body %q: status = %d, want 400", body, rec.Code)
		}
	}
}

func TestBrokenReleaseFailsJobsButStaysLive(t *testing.T) {
	buildinfo.BrokenRelease = "true"
	t.Cleanup(func() { buildinfo.BrokenRelease = "false" })

	h := newTestServer(t, &fakeStore{}, "")
	if rec := do(t, h, http.MethodGet, "/healthz", ""); rec.Code != http.StatusOK {
		t.Fatalf("broken release must keep liveness green, got %d", rec.Code)
	}
	if rec := do(t, h, http.MethodPost, "/jobs", `{"payload":"x"}`); rec.Code != http.StatusInternalServerError {
		t.Fatalf("broken release must fail job submission, got %d", rec.Code)
	}
}

func TestStatusAggregatesWorker(t *testing.T) {
	worker := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"service":"worker","version":"1.2.3"}`))
	}))
	defer worker.Close()

	rec := do(t, newTestServer(t, &fakeStore{}, worker.URL), http.MethodGet, "/status", "")
	var body struct {
		Services []ServiceStatus `json:"services"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(body.Services) != 3 {
		t.Fatalf("want api, keyvalue and worker, got %d services", len(body.Services))
	}
	if w := body.Services[2]; w.Name != "worker" || !w.Healthy || w.State != "up" {
		t.Fatalf("unexpected worker status: %+v", w)
	}
}

func TestStatusMarksUnreachableWorkerAsWaking(t *testing.T) {
	rec := do(t, newTestServer(t, &fakeStore{}, "http://127.0.0.1:1"), http.MethodGet, "/status", "")
	if !strings.Contains(rec.Body.String(), `"state":"waking"`) {
		t.Fatalf("unreachable worker should be reported as waking: %s", rec.Body)
	}
}

func TestCORSPreflight(t *testing.T) {
	rec := do(t, newTestServer(t, &fakeStore{}, ""), http.MethodOptions, "/status", "")
	if rec.Code != http.StatusNoContent || rec.Header().Get("Access-Control-Allow-Origin") != "*" {
		t.Fatalf("preflight failed: %d %v", rec.Code, rec.Header())
	}
}

func TestRequestIDIsSanitised(t *testing.T) {
	h := newTestServer(t, &fakeStore{}, "")
	cases := map[string]bool{
		"abc-123":                    true,
		"fake\nlevel=ERROR msg=hack": false,
		strings.Repeat("a", 65):      false,
	}
	for id, kept := range cases {
		req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
		req.Header.Set("X-Request-ID", id)
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		got := rec.Header().Get("X-Request-ID")
		if kept && got != id {
			t.Errorf("valid id %q was replaced with %q", id, got)
		}
		if !kept && (got == id || got == "") {
			t.Errorf("unsafe id %q was not replaced, got %q", id, got)
		}
	}
}
