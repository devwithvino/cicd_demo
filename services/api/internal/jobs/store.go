// Package jobs stores jobs in Key Value and hands them to the worker queue.
//
// Key layout (every key starts with the environment prefix, for example "stg:"):
//
//	{prefix}job:{id}       JSON document for one job, expires after a day
//	{prefix}queue          list the worker pops jobs from
//	{prefix}jobs:recent    list of the most recent job IDs, newest first
package jobs

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// Job statuses shared with the worker.
const (
	StatusQueued     = "queued"
	StatusProcessing = "processing"
	StatusDone       = "done"
	StatusFailed     = "failed"
)

const (
	jobTTL       = 24 * time.Hour
	recentLength = 20
)

// ErrNotFound is returned when a job ID does not exist.
var ErrNotFound = errors.New("job not found")

// Job is one unit of work flowing from the API to the worker.
type Job struct {
	ID          string `json:"id"`
	Payload     string `json:"payload"`
	Status      string `json:"status"`
	Result      string `json:"result,omitempty"`
	CreatedAt   string `json:"createdAt"`
	CompletedAt string `json:"completedAt,omitempty"`
	SubmittedBy string `json:"submittedBy"`
	ProcessedBy string `json:"processedBy,omitempty"`
}

// Store persists jobs and enqueues them for the worker.
type Store struct {
	client *redis.Client
	prefix string
}

// NewStore creates a store using the given client and key prefix.
func NewStore(client *redis.Client, prefix string) *Store {
	return &Store{client: client, prefix: prefix}
}

// Ping checks that Key Value is reachable.
func (s *Store) Ping(ctx context.Context) error {
	return s.client.Ping(ctx).Err()
}

// Create saves a new job and pushes it onto the worker queue.
func (s *Store) Create(ctx context.Context, payload, submittedBy string) (Job, error) {
	id, err := newID()
	if err != nil {
		return Job{}, err
	}
	job := Job{
		ID:          id,
		Payload:     payload,
		Status:      StatusQueued,
		CreatedAt:   time.Now().UTC().Format(time.RFC3339Nano),
		SubmittedBy: submittedBy,
	}
	doc, err := json.Marshal(job)
	if err != nil {
		return Job{}, err
	}
	pipe := s.client.TxPipeline()
	pipe.Set(ctx, s.key("job:"+id), doc, jobTTL)
	pipe.LPush(ctx, s.key("queue"), id)
	pipe.LPush(ctx, s.key("jobs:recent"), id)
	pipe.LTrim(ctx, s.key("jobs:recent"), 0, recentLength-1)
	if _, err := pipe.Exec(ctx); err != nil {
		return Job{}, fmt.Errorf("enqueue job: %w", err)
	}
	return job, nil
}

// Get returns one job by ID.
func (s *Store) Get(ctx context.Context, id string) (Job, error) {
	doc, err := s.client.Get(ctx, s.key("job:"+id)).Bytes()
	if errors.Is(err, redis.Nil) {
		return Job{}, ErrNotFound
	}
	if err != nil {
		return Job{}, err
	}
	var job Job
	if err := json.Unmarshal(doc, &job); err != nil {
		return Job{}, fmt.Errorf("decode job %s: %w", id, err)
	}
	return job, nil
}

// Recent returns the most recent jobs, newest first. Expired jobs are skipped.
func (s *Store) Recent(ctx context.Context) ([]Job, error) {
	ids, err := s.client.LRange(ctx, s.key("jobs:recent"), 0, recentLength-1).Result()
	if err != nil {
		return nil, err
	}
	jobs := make([]Job, 0, len(ids))
	for _, id := range ids {
		job, err := s.Get(ctx, id)
		if errors.Is(err, ErrNotFound) {
			continue
		}
		if err != nil {
			return nil, err
		}
		jobs = append(jobs, job)
	}
	return jobs, nil
}

// QueueDepth returns how many jobs are waiting for the worker.
func (s *Store) QueueDepth(ctx context.Context) (int64, error) {
	return s.client.LLen(ctx, s.key("queue")).Result()
}

func (s *Store) key(name string) string {
	return s.prefix + name
}

func newID() (string, error) {
	buf := make([]byte, 8)
	if _, err := rand.Read(buf); err != nil {
		return "", fmt.Errorf("generate job id: %w", err)
	}
	return hex.EncodeToString(buf), nil
}
