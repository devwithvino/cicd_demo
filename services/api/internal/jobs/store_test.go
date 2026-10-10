package jobs

import (
	"context"
	"errors"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func newTestStore(t *testing.T) (*Store, *miniredis.Miniredis) {
	t.Helper()
	mr := miniredis.RunT(t)
	client := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	t.Cleanup(func() { _ = client.Close() })
	return NewStore(client, "test:"), mr
}

func TestCreateQueuesJobUnderPrefix(t *testing.T) {
	store, mr := newTestStore(t)
	ctx := context.Background()

	job, err := store.Create(ctx, "hello", "api 1.0.0")
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if job.Status != StatusQueued || job.ID == "" {
		t.Fatalf("unexpected job: %+v", job)
	}

	queued, err := mr.List("test:queue")
	if err != nil || len(queued) != 1 || queued[0] != job.ID {
		t.Fatalf("queue = %v, err = %v, want [%s]", queued, err, job.ID)
	}
	if !mr.Exists("test:job:" + job.ID) {
		t.Fatal("job document not stored under the environment prefix")
	}
	if ttl := mr.TTL("test:job:" + job.ID); ttl <= 0 {
		t.Fatalf("job document has no expiry, ttl = %v", ttl)
	}
}

func TestGetReturnsNotFound(t *testing.T) {
	store, _ := newTestStore(t)
	if _, err := store.Get(context.Background(), "missing"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("err = %v, want ErrNotFound", err)
	}
}

func TestRecentIsNewestFirstAndCapped(t *testing.T) {
	store, _ := newTestStore(t)
	ctx := context.Background()

	var last Job
	for i := 0; i < recentLength+5; i++ {
		job, err := store.Create(ctx, "payload", "api test")
		if err != nil {
			t.Fatalf("Create: %v", err)
		}
		last = job
	}

	recent, err := store.Recent(ctx)
	if err != nil {
		t.Fatalf("Recent: %v", err)
	}
	if len(recent) != recentLength {
		t.Fatalf("len(recent) = %d, want %d", len(recent), recentLength)
	}
	if recent[0].ID != last.ID {
		t.Fatalf("newest job should come first")
	}
}

func TestRecentSkipsExpiredJobs(t *testing.T) {
	store, mr := newTestStore(t)
	ctx := context.Background()

	job, _ := store.Create(ctx, "will expire", "api test")
	mr.Del("test:job:" + job.ID)

	recent, err := store.Recent(ctx)
	if err != nil {
		t.Fatalf("Recent: %v", err)
	}
	if len(recent) != 0 {
		t.Fatalf("expired job should be skipped, got %d jobs", len(recent))
	}
}

func TestQueueDepth(t *testing.T) {
	store, _ := newTestStore(t)
	ctx := context.Background()
	for i := 0; i < 3; i++ {
		_, _ = store.Create(ctx, "x", "api test")
	}
	depth, err := store.QueueDepth(ctx)
	if err != nil || depth != 3 {
		t.Fatalf("depth = %d, err = %v, want 3", depth, err)
	}
}
