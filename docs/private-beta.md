# Private beta operations

The beta uses PostgreSQL for accounts, hashed sessions, private workspace JSON,
single-use invitations, login throttling, and daily AI usage. The map server stays
stateless: replicas share the database and the same packaged dataset versions.

Passwords use Argon2id. Session cookies are HttpOnly, SameSite Strict, and Secure
in production; sessions expire after seven days. Invitations expire after 24
hours. Registration requires an invitation bound to the supplied email. There
is no public sign-up or self-service password reset in this beta. Administrators
can revoke sessions with `python -m autocarto.web.admin revoke-sessions --email EMAIL`.

Signed-in workspaces autosave after one second without changes. The latest saved
project opens on return; Projects lists all owned projects. Wait for **Saved to
your account** before closing. Workspace JSON export remains available as a local
backup. Writes carry a revision: an outdated tab receives 409 and stops autosaving
until the user reopens a server copy. Export unsaved changes before reopening.
Dataset or validation-engine drift fails closed when a saved map is opened.

`AUTOCARTO_AI_DAILY_LIMIT` defaults to 20 attempted AI calls per user per UTC day.
The shared, atomic counter survives restarts and additional replicas. Provider
failures count as attempts; guided maps use no AI quota. A separate per-process
limit allows two active chat calls and returns 429 when busy. Login is limited
to ten attempts per email per 15-minute window, and two simultaneous password
hash operations per process. These limits protect the small beta instance; they
are not billing caps. Ordinary POST/PUT bodies are limited to 16 KiB (413);
workspace imports allow 1 MiB and project envelopes allow an extra 4 KiB.

## Local PostgreSQL acceptance environment

Set `BETA_DB_PASSWORD` to a random URL-safe value in the process environment.
Run `docker compose -f compose.beta.yml up -d --build`. This builds the Linux
image, starts PostgreSQL 16, runs schema migration v1, and serves the authenticated
beta at `http://127.0.0.1:8001`. The database has no exposed host port and uses a
named volume. Do not use `down -v` unless deliberately deleting all local beta data.
The original `compose.web.yml` remains a local demonstration without accounts.

Use the admin CLI in the web container to create an invitation, writing its
output to a private file under `/tmp`, then copy it to a gitignored local file.
Do not put invitations in URLs, terminal history, logs, commits, or documentation.
Deliver codes privately only when explicitly authorized. The recipient chooses
their own password on **Have an invitation? Join the beta**.

## Render deployment

`render.yaml` specifies one web instance and one private PostgreSQL instance in
Virginia. Current plan IDs are `0.5c-512mb` ($7/month, formerly Starter) and
`0.1c-256mb` ($6/month, formerly Basic-256mb). Compute starts at $13/month;
the explicit 1 GB database allocation adds $0.30/month at $0.30/GB. The expected
starting total is therefore **$13.30/month before bandwidth, taxes, or other
workspace charges**, within the authorized $40/month ceiling. No autoscaling,
paid preview environments, or automatic deploys are configured. The ceiling is
an operational budget, not a provider-enforced hard spending cap.

Before enabling a larger instance, inspect measured memory/CPU, errors, and
concurrency. The 1 CPU/2 GB web option is $25/month, bringing compute to $31
before storage. Review actual billing in Render rather than assuming quotas
prevent overage. See [Render pricing](https://render.com/pricing) and
[Blueprint specification](https://render.com/docs/blueprint-spec).

Deploy from the reviewed repository revision with Dockerfile.web. The predeploy
command runs `python -m autocarto.web.admin migrate`. Set `AUTOCARTO_PUBLIC_URL`
to the exact HTTPS origin, `SENTRY_DSN` to the beta Sentry project, and
`NVIDIA_API_KEY` through Render's secret environment settings. DATABASE_URL uses
the private managed database connection. Production startup refuses missing
monitoring, non-HTTPS origins, SQLite, or an unmigrated database.

Sentry is opt-in locally and required in production. Reports omit request bodies,
headers, user details, breadcrumbs, locals, and exception messages. Failures return
a correlation ID; server logs contain only this ID and the exception class.
Verify a synthetic error appears in the real Sentry project before inviting users.
Do not send test prompts containing private information to verify monitoring.

`constraints-web-linux.txt` pins the native and account/monitoring dependencies
tested in Linux. The full Python dependency graph and base-image tags are not
locked; rebuilds require the regression and Docker acceptance checks below.

## Acceptance

Run the web CI suite, build the image, migrate a fresh PostgreSQL database, and
test invitation sign-in, two-user isolation, revision conflicts, shared quota
increments, and restore after restarting the server. Then a real invited user
must sign in, create a map, close the tab, return, and see the saved map. Local
synthetic-account checks alone do not complete that final acceptance condition.
