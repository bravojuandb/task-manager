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
no JavaScript framework is required. A small script toggles order-specific fields.
Dates include the database-returned timezone.

## Orders and price requests

Contacts are stored in `customer`, `supplier` or `other`; `recipient` is removed.
Customer and supplier fields are visible for every task type. Non-order tasks
require at least one contact and may contain customer, supplier and other together.
Orders still require both customer and supplier. Only orders use placed/delivered
flags. The API accepts the contact columns directly, for example:

```json
{"task_type": "email", "other": "Example contact", "description": "Send an update"}
```

Select `order` to enter both customer and supplier. Orders
require both names. Unchecked progress flags mean pending; placed means in progress;
delivered means completed and sets the completion timestamp. Delivered requires
placed. Completed orders cannot be reopened; editing their details keeps the
original completion timestamp. The ordinary status endpoint rejects order changes:
use the detail form (or PUT details) with the order flags instead.

For existing databases, apply `002_order_details.sql` and then
`003_contact_roles.sql`, each once in a transaction. Migration 002 has already
been applied on k8. Stop the application before 003 because the running code
still references the column it removes. A fresh database should use
`sql/schema.sql` directly, without these migrations.

```bash
sudo systemctl stop k8-task-manager.service && \
psql -h 127.0.0.1 -U k8_app -d task_manager -W \
  -v ON_ERROR_STOP=1 --single-transaction -f sql/003_contact_roles.sql && \
sudo systemctl start k8-task-manager.service
```

Migration 003 moves quotation recipients into customer and price-request
recipients into supplier. Other old recipients, including unclassified order
contacts, go provisionally into other to preserve their names. Review those
contacts and select the correct role when editing. Already populated order
customers and suppliers are retained. No progress flags are inferred. Edit each
old order to supply the real parties and flags; completed orders must remain
delivered. The migration uses
`CHECK ... NOT VALID`: new and edited rows must follow the rules immediately,
while untouched old rows are retained. After all old orders are corrected, run:

```sql
ALTER TABLE tasks VALIDATE CONSTRAINT tasks_parties_consistent;
ALTER TABLE tasks VALIDATE CONSTRAINT tasks_order_progress_consistent;
```

To run the optional database tests as well as the regular tests:

```bash
K8_TEST_DATABASE=1 .venv/bin/python -m unittest discover -s tests -v
```

These database tests use temporary tables on their own connections and roll back
all synthetic data. They require the configured application database connection.

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

## Flexible contacts (migration 004)

After migration 003, apply `sql/004_flexible_contacts.sql` once in a transaction,
then restart the service. It relaxes the contact constraint for non-order tasks;
no task data is changed. Existing orders awaiting classification are retained.
Fresh databases use the current `sql/schema.sql` and do not run migrations.

## Task list sorting

Tasks are ordered by `created_at ASC, task_id ASC` (oldest first) by default.
Choose **Newest first** in the list, or use `GET /tasks?sort=newest`. The sort
combines with the status filter and is preserved when changing status or deleting.

The web homepage defaults to **Pending**, oldest first. Select **All statuses**
(or visit `/?status=`) to view all tasks. The JSON API still lists all statuses
when its status parameter is omitted.
