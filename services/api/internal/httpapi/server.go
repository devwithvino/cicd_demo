// Package httpapi exposes the API service over HTTP.
package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/getsentry/sentry-go"
	sentryhttp "github.com/getsentry/sentry-go/http"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/devwithvino/cicd_demo/services/api/internal/buildinfo"
	"github.com/devwithvino/cicd_demo/services/api/internal/config"
	"github.com/devwithvino/cicd_demo/services/api/internal/jobs"
)

const maxPayloadBytes = 4 << 10

// JobStore is the subset of the job store the handlers need.
type JobStore interface {
	Ping(ctx context.Context) error
	Create(ctx context.Context, payload, submittedBy string) (jobs.Job, error)
	Get(ctx context.Context, id string) (jobs.Job, error)
	Recent(ctx context.Context) ([]jobs.Job, error)
	QueueDepth(ctx context.Context) (int64, error)
}

// Server holds the dependencies shared by all handlers.
type Server struct {
	cfg    config.Config
	store  JobStore
	logger *slog.Logger
	client *http.Client
}

// New creates a server.
func New(cfg config.Config, store JobStore, logger *slog.Logger) *Server {
	return &Server{
		cfg:    cfg,
		store:  store,
		logger: logger,
		client: &http.Client{Timeout: 3 * time.Second},
	}
}

// Handler returns the full routing table.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	routes := map[string]http.HandlerFunc{
		"GET /healthz":   s.healthz,
		"GET /readyz":    s.readyz,
		"GET /version":   s.version,
		"GET /status":    s.status,
		"POST /jobs":     s.createJob,
		"GET /jobs":      s.listJobs,
		"GET /jobs/{id}": s.getJob,
	}
	for pattern, handler := range routes {
		route := pattern[strings.Index(pattern, " ")+1:]
		mux.Handle(pattern, instrument(route, s.logger, handler))
	}
	mux.Handle("GET /metrics", promhttp.Handler())
	// Sentry recovers panics and reports them. Without a DSN it does nothing.
	return cors(sentryhttp.New(sentryhttp.Options{Repanic: false}).Handle(mux))
}

// VersionInfo describes exactly which build is running and where.
type VersionInfo struct {
	Service       string `json:"service"`
	Version       string `json:"version"`
	Commit        string `json:"commit"`
	CommitURL     string `json:"commitUrl,omitempty"`
	BuildTime     string `json:"buildTime"`
	Environment   string `json:"environment"`
	ImageRef      string `json:"imageRef,omitempty"`
	StartedAt     string `json:"startedAt"`
	UptimeSeconds int64  `json:"uptimeSeconds"`
}

func (s *Server) versionInfo() VersionInfo {
	info := VersionInfo{
		Service:       "api",
		Version:       buildinfo.Version,
		Commit:        buildinfo.Commit,
		BuildTime:     buildinfo.BuildTime,
		Environment:   s.cfg.Environment,
		ImageRef:      s.cfg.ImageRef,
		StartedAt:     buildinfo.StartedAt.Format(time.RFC3339),
		UptimeSeconds: int64(time.Since(buildinfo.StartedAt).Seconds()),
	}
	if s.cfg.RepoURL != "" && buildinfo.Commit != "unknown" {
		info.CommitURL = s.cfg.RepoURL + "/commit/" + buildinfo.Commit
	}
	return info
}

func (s *Server) healthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) readyz(w http.ResponseWriter, r *http.Request) {
	if err := s.store.Ping(r.Context()); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "unavailable", "reason": "key value unreachable"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *Server) version(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, s.versionInfo())
}

// ServiceStatus is one entry in the aggregated status response.
type ServiceStatus struct {
	Name    string          `json:"name"`
	Healthy bool            `json:"healthy"`
	State   string          `json:"state"`
	Version json.RawMessage `json:"version,omitempty"`
	Error   string          `json:"error,omitempty"`
}

// status aggregates the health of the API, Key Value and the worker.
// Calling the worker also wakes it if the free tier has spun it down.
func (s *Server) status(w http.ResponseWriter, r *http.Request) {
	self, _ := json.Marshal(s.versionInfo())
	services := []ServiceStatus{{Name: "api", Healthy: true, State: "up", Version: self}}

	kv := ServiceStatus{Name: "keyvalue", Healthy: true, State: "up"}
	if err := s.store.Ping(r.Context()); err != nil {
		kv = ServiceStatus{Name: "keyvalue", State: "down", Error: "unreachable"}
	}
	services = append(services, kv, s.workerStatus(r.Context()))

	depth, _ := s.store.QueueDepth(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{
		"environment": s.cfg.Environment,
		"queueDepth":  depth,
		"services":    services,
		"checkedAt":   time.Now().UTC().Format(time.RFC3339),
	})
}

func (s *Server) workerStatus(ctx context.Context) ServiceStatus {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.cfg.WorkerURL+"/version", nil)
	if err != nil {
		return ServiceStatus{Name: "worker", State: "down", Error: err.Error()}
	}
	resp, err := s.client.Do(req)
	if err != nil {
		// A timeout usually means the free instance is cold starting.
		return ServiceStatus{Name: "worker", State: "waking", Error: "no response yet, the instance may be starting"}
	}
	defer func() { _ = resp.Body.Close() }()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 16<<10))
	if resp.StatusCode != http.StatusOK || !json.Valid(body) {
		return ServiceStatus{Name: "worker", State: "down", Error: resp.Status}
	}
	return ServiceStatus{Name: "worker", Healthy: true, State: "up", Version: body}
}

type createJobRequest struct {
	Payload string `json:"payload"`
}

func (s *Server) createJob(w http.ResponseWriter, r *http.Request) {
	if buildinfo.IsBroken() {
		// Deliberate defect for the rollback demo. Liveness stays green, so the
		// platform keeps the release, and only the pipeline smoke test catches it.
		reportError(r, errors.New("job submission is broken in this release"))
		writeError(w, http.StatusInternalServerError, "job submission is broken in this release")
		return
	}
	var req createJobRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxPayloadBytes)).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "body must be JSON like {\"payload\": \"text\"}")
		return
	}
	req.Payload = strings.TrimSpace(req.Payload)
	if req.Payload == "" {
		writeError(w, http.StatusBadRequest, "payload must not be empty")
		return
	}
	job, err := s.store.Create(r.Context(), req.Payload, "api "+buildinfo.Version)
	if err != nil {
		s.logger.Error("create job failed", "error", err)
		reportError(r, err)
		writeError(w, http.StatusServiceUnavailable, "could not queue job")
		return
	}
	writeJSON(w, http.StatusAccepted, job)
}

func (s *Server) getJob(w http.ResponseWriter, r *http.Request) {
	job, err := s.store.Get(r.Context(), r.PathValue("id"))
	if errors.Is(err, jobs.ErrNotFound) {
		writeError(w, http.StatusNotFound, "job not found")
		return
	}
	if err != nil {
		s.logger.Error("get job failed", "error", err)
		reportError(r, err)
		writeError(w, http.StatusServiceUnavailable, "could not read job")
		return
	}
	writeJSON(w, http.StatusOK, job)
}

func (s *Server) listJobs(w http.ResponseWriter, r *http.Request) {
	recent, err := s.store.Recent(r.Context())
	if err != nil {
		s.logger.Error("list jobs failed", "error", err)
		reportError(r, err)
		writeError(w, http.StatusServiceUnavailable, "could not list jobs")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"jobs": recent})
}

func writeJSON(w http.ResponseWriter, code int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, code int, message string) {
	writeJSON(w, code, map[string]string{"error": message})
}

// reportError sends an error to Sentry with the request attached. It is a
// no op when Sentry is not configured.
func reportError(r *http.Request, err error) {
	if hub := sentry.GetHubFromContext(r.Context()); hub != nil {
		hub.CaptureException(err)
		return
	}
	sentry.CaptureException(err)
}
