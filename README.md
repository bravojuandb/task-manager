# task-manager
Private App for task management. Hosted in personal server, with HTML, FastAPI and PostgreSQL

## Run locally

Configure the ignored `.env` using `.env.example`, then run:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1
```

Open http://127.0.0.1:8000/ for the task interface, or `/docs` for the JSON API.
When working over SSH, forward port 8000 to your development computer.

The interface has a task list with optional status filtering and creation-date sorting and a shared create/edit
form. Completed tasks can have their details edited but cannot be reopened. Deletion
requires expanding the confirmation panel and choosing “Yes, delete task”.

## How a form reaches the database

1. A browser submits named form fields to a `/ui/tasks/...` route in `app/web.py`.
2. A Pydantic model validates the values and strips surrounding whitespace.
3. The route calls the existing Python task operation in `app/main.py` directly.
4. Psycopg passes SQL and parameter values separately to PostgreSQL.
5. The transaction commits on success or rolls back on an exception.
6. A successful form submission returns HTTP 303, redirecting to the task list.
   Validation errors redisplay the form with the submitted values and field errors.

Jinja2 escapes task text when rendering HTML. The UI uses plain HTML forms and CSS;
no JavaScript framework is required. Dates include the database-returned timezone.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## Run as a systemd service on k8

`deploy/k8-task-manager.service` is configured for user `bravojuandb` and the
checkout at `/home/bravojuandb/projects/task-manager`. Adjust those paths and the
user/group if installing elsewhere. The application loads the existing `.env`
through python-dotenv; no credentials belong in the service file.

Stop the development Uvicorn process with Ctrl+C first, to free port 8000.
From the project directory, install and enable the service:

```bash
chmod 600 .env
sudo install -m 644 deploy/k8-task-manager.service /etc/systemd/system/k8-task-manager.service
sudo systemctl daemon-reload
sudo systemctl enable --now k8-task-manager.service
systemctl status k8-task-manager.service --no-pager
curl --fail http://127.0.0.1:8000/ -o /dev/null
```

The service runs as the regular application user, starts at boot independently
of SSH sessions, and restarts after a failure. Uvicorn listens on loopback only.
It does not use development auto-reload. PostgreSQL data stays in PostgreSQL;
restarting this service does not remove tasks.

Useful commands:

```bash
journalctl -u k8-task-manager.service -n 50 --no-pager
journalctl -u k8-task-manager.service -f
sudo systemctl restart k8-task-manager.service
sudo systemctl stop k8-task-manager.service
```

After changing Python code, restart the service. It runs this checkout, so branch
changes also affect the deployed files. Keep development on a separate port
(for example `--port 8001`) or stop the service before using port 8000.

To disable automatic startup and return to manual operation:

```bash
sudo systemctl disable --now k8-task-manager.service
```

For Data Engineering: `ExecStart` selects the executable, `WorkingDirectory`
sets its context, `.env` supplies configuration, `Restart` handles process
failures, and the journal collects logs. The same concepts apply to running
data pipelines reliably, although scheduled jobs often use systemd timers.

## Task list sorting

Tasks are ordered by `created_at ASC, task_id ASC` (oldest first) by default.
Choose **Newest first** in the list, or use `GET /tasks?sort=newest`. The sort
combines with the status filter and is preserved when changing status or deleting.

The web homepage defaults to **Pending**, oldest first. Select **All statuses**
(or visit `/?status=`) to view all tasks. The JSON API still lists all statuses
when its status parameter is omitted.
