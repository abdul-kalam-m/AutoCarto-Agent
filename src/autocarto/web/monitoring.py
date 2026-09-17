"""Error IDs and optional Sentry reporting without prompts, credentials or locals."""
import logging
import json
import os
import uuid

log = logging.getLogger("cartollm.errors")


def scrub_event(event, hint):
    for key in ("request", "user", "breadcrumbs", "extra", "contexts", "logentry"):
        event.pop(key, None)
    event.pop("message", None)
    for exception in event.get("exception", {}).get("values", []):
        exception["value"] = "Details withheld; correlate using the error ID"
        for frame in exception.get("stacktrace", {}).get("frames", []):
            frame.pop("vars", None)
    return event


def configure():
    if os.getenv("SENTRY_DSN"):
        import sentry_sdk
        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], environment=os.getenv("AUTOCARTO_DEPLOYMENT", "local"), release=os.getenv("RENDER_GIT_COMMIT", "cartollm-beta"), send_default_pii=False, include_local_variables=False, default_integrations=False, traces_sample_rate=0, before_send=scrub_event)


def report_error(error):
    error_id = str(uuid.uuid4())
    log.error(json.dumps({"event": "application_error", "error_id": error_id, "error_type": type(error).__name__}))
    if os.getenv("SENTRY_DSN"):
        import sentry_sdk
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("error_id", error_id)
            sentry_sdk.capture_exception(error)
    return error_id
