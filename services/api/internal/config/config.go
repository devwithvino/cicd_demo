// Package config reads runtime settings from environment variables.
//
// Runtime settings are what make one image deployable anywhere: the image is
// identical in every environment, only these values change.
package config

import (
	"os"
	"strings"
)

// Config is the runtime configuration of the API service.
type Config struct {
	Port        string
	Environment string
	KVURL       string
	KeyPrefix   string
	WorkerURL   string
	ImageRef    string
	RepoURL     string
	SentryDSN   string
}

// Load reads configuration from the environment, applying local defaults.
func Load() Config {
	return Config{
		Port:        get("PORT", "8080"),
		Environment: get("APP_ENV", "local"),
		KVURL:       get("KV_URL", "redis://localhost:6379/0"),
		KeyPrefix:   get("KEY_PREFIX", "local:"),
		WorkerURL:   strings.TrimRight(get("WORKER_URL", "http://localhost:8081"), "/"),
		ImageRef:    get("IMAGE_REF", ""),
		RepoURL:     strings.TrimRight(get("REPO_URL", ""), "/"),
		SentryDSN:   get("SENTRY_DSN", ""),
	}
}

func get(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok && value != "" {
		return value
	}
	return fallback
}
