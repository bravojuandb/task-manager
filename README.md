# task-manager
Private App for task management. Hosted in personal server, with HTML, FastAPI and PostgreSQL

## Run locally

Configure the ignored `.env` using `.env.example`, then run:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1
```

Open http://127.0.0.1:8000/ for the task interface, or `/docs` for the JSON API.
When working over SSH, forward port 8000 to your development computer.

The interface has a task list with optional status filtering and a shared create/edit
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
