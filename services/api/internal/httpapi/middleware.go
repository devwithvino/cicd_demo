package httpapi

import (
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var validRequestID = regexp.MustCompile(`^[A-Za-z0-9._-]{1,64}$`)

var (
	requestsTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "shipyard_http_requests_total",
		Help: "HTTP requests handled, by route and status code.",
	}, []string{"service", "route", "code"})

	requestDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "shipyard_http_request_duration_seconds",
		Help:    "HTTP request latency, by route.",
		Buckets: prometheus.DefBuckets,
	}, []string{"service", "route"})
)

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

// instrument wraps a handler with request IDs, access logs and metrics.
func instrument(route string, logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		requestID := safeRequestID(r.Header.Get("X-Request-ID"))
		w.Header().Set("X-Request-ID", requestID)

		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)

		elapsed := time.Since(start)
		requestsTotal.WithLabelValues("api", route, strconv.Itoa(rec.status)).Inc()
		requestDuration.WithLabelValues("api", route).Observe(elapsed.Seconds())
		logger.Info("request",
			"request_id", requestID,
			"method", safeMethod(r.Method),
			"route", route,
			"status", rec.status,
			"duration_ms", elapsed.Milliseconds(),
		)
	})
}

// cors lets the static status page read public endpoints from the browser.
func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// Values that reach the logs from a client are reduced to known safe forms,
// so a caller can never inject fake log entries.
var (
	stripLineBreaks = strings.NewReplacer("\n", "", "\r", "")
	knownMethods    = map[string]bool{
		http.MethodGet: true, http.MethodHead: true, http.MethodPost: true, http.MethodPut: true,
		http.MethodPatch: true, http.MethodDelete: true, http.MethodOptions: true,
	}
)

// safeRequestID keeps a caller supplied ID only when it is short and plain.
func safeRequestID(id string) string {
	if !validRequestID.MatchString(id) {
		return newRequestID()
	}
	return stripLineBreaks.Replace(id)
}

func safeMethod(method string) string {
	if knownMethods[method] {
		return method
	}
	return "OTHER"
}

func newRequestID() string {
	buf := make([]byte, 8)
	if _, err := rand.Read(buf); err != nil {
		return "unknown"
	}
	return hex.EncodeToString(buf)
}
