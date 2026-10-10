from unittest import mock

from shipyard_worker.config import Config
from shipyard_worker.monitoring import init_sentry, release


def make_config(dsn: str = "") -> Config:
    return Config(
        port=0,
        environment="staging",
        kv_url="redis://unused",
        key_prefix="stg:",
        repo_url="",
        version="1.2.3",
        commit="abc",
        build_time="t",
        sentry_dsn=dsn,
    )


def test_disabled_without_dsn() -> None:
    with mock.patch("sentry_sdk.init") as init:
        assert init_sentry(make_config()) is False
        init.assert_not_called()


def test_enabled_with_dsn_uses_release_and_environment() -> None:
    with mock.patch("sentry_sdk.init") as init, mock.patch("sentry_sdk.set_tag"):
        assert init_sentry(make_config("https://public@example.ingest.sentry.io/1")) is True
    kwargs = init.call_args.kwargs
    assert kwargs["environment"] == "staging"
    assert kwargs["release"] == "shipyard@1.2.3"
    assert kwargs["send_default_pii"] is False


def test_release_name() -> None:
    assert release(make_config()) == "shipyard@1.2.3"
