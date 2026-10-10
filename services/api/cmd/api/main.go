// Command api runs the Shipyard API service.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/devwithvino/cicd_demo/services/api/internal/buildinfo"
	"github.com/devwithvino/cicd_demo/services/api/internal/config"
	"github.com/devwithvino/cicd_demo/services/api/internal/httpapi"
	"github.com/devwithvino/cicd_demo/services/api/internal/jobs"
	"github.com/devwithvino/cicd_demo/services/api/internal/monitoring"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil)).With("service", "api")
	if err := run(logger); err != nil {
		logger.Error("api stopped with error", "error", err)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	cfg := config.Load()

	enabled, err := monitoring.Init(cfg)
	if err != nil {
		logger.Warn("sentry disabled: could not initialise", "error", err)
	}
	if enabled {
		logger.Info("sentry error reporting enabled", "release", monitoring.Release())
		defer monitoring.Flush()
	}

	opts, err := redis.ParseURL(cfg.KVURL)
	if err != nil {
		return err
	}
	client := redis.NewClient(opts)
	defer func() {
		if err := client.Close(); err != nil {
			logger.Warn("closing key value client failed", "error", err)
		}
	}()

	server := httpapi.New(cfg, jobs.NewStore(client, cfg.KeyPrefix), logger)
	httpServer := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           server.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	errs := make(chan error, 1)
	go func() {
		logger.Info("api listening",
			"port", cfg.Port,
			"environment", cfg.Environment,
			"version", buildinfo.Version,
			"commit", buildinfo.Commit,
		)
		errs <- httpServer.ListenAndServe()
	}()

	select {
	case err := <-errs:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-ctx.Done():
		logger.Info("shutdown signal received, draining connections")
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	return httpServer.Shutdown(shutdownCtx)
}
