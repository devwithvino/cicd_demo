package httpapi

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// FuzzSafeRequestID checks that no caller supplied value can reach the logs
// unless it is short and plain. Run longer with:
//
//	go test -fuzz=FuzzSafeRequestID ./internal/httpapi
func FuzzSafeRequestID(f *testing.F) {
	for _, seed := range []string{"", "abc-123", "a\nb", "x\r\nlevel=ERROR", strings.Repeat("z", 200), "日本語"} {
		f.Add(seed)
	}
	f.Fuzz(func(t *testing.T, input string) {
		got := safeRequestID(input)
		if !validRequestID.MatchString(got) {
			t.Fatalf("unsafe request ID %q produced from %q", got, input)
		}
		if strings.ContainsAny(got, "\r\n") {
			t.Fatalf("line break survived in %q", got)
		}
	})
}

// FuzzCreateJob sends arbitrary bodies to POST /jobs. Whatever arrives, the
// API must answer with a clean client error or accept the job, never crash or
// return a server error.
func FuzzCreateJob(f *testing.F) {
	for _, seed := range []string{`{"payload":"ship it"}`, `{"payload":""}`, `{}`, `not json`, `{"payload":123}`, `[`, ""} {
		f.Add([]byte(seed))
	}
	h := newTestServer(f, &fakeStore{}, "")
	f.Fuzz(func(t *testing.T, body []byte) {
		req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewReader(body))
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != http.StatusAccepted && rec.Code != http.StatusBadRequest {
			t.Fatalf("body %q gave status %d", body, rec.Code)
		}
	})
}
