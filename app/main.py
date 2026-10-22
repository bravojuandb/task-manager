from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.db import get_connection
from app.models import TaskCreate, TaskStatusUpdate
from app.web import create_web_router

app = FastAPI(title="k8 Task Manager", docs_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/docs", include_in_schema=False)
def documentation():
    page = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_favicon_url="data:,",
    )
    # Invert Swagger's light theme while retaining familiar method colors.
    style = """
    <style>
        html { background: #000; }
        body {
            margin: 0;
            min-height: 100vh;
            background: #fff;
            filter: invert(1) hue-rotate(180deg);
        }
    </style>
    """
    return HTMLResponse(page.body.decode("utf-8").replace("</head>", style + "</head>"))

@app.post("/tasks", status_code=201)
def create_task(task: TaskCreate):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (task_type, recipient, description)
                VALUES (%s, %s, %s)
                RETURNING *;
                """,
                (task.task_type, task.recipient, task.description),
            )
            created_task = cursor.fetchone()

    return created_task

@app.get("/tasks")
def list_tasks(
    status: Literal["pending", "in_progress", "completed"] | None = None,
    sort: Literal["oldest", "newest"] = "oldest",
):
    # SQL keywords cannot be value parameters: choose only fixed directions.
    direction = {"oldest": "ASC", "newest": "DESC"}[sort]
    query = "SELECT * FROM tasks"
    parameters = ()
    if status is not None:
        query += " WHERE status = %s"
        parameters = (status,)
    query += f" ORDER BY created_at {direction}, task_id {direction}"
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            tasks = cursor.fetchall()

    return tasks


@app.get("/tasks/{task_id}")
def retrieve_task(task_id: int):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT *
                FROM tasks
                WHERE task_id = %s;
                """,
                (task_id,),
            )
            task = cursor.fetchone()

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task

@app.patch("/tasks/{task_id}")
def update_task_status(task_id: int, update: TaskStatusUpdate):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tasks WHERE task_id = %s FOR UPDATE;",
                (task_id,),
            )
            task = cursor.fetchone()
            if task is None:
                raise HTTPException(status_code=404, detail="Task not found")

            if task["status"] == "completed":
                if update.status != "completed":
                    raise HTTPException(
                        status_code=409, detail="Completed tasks cannot be reopened"
                    )
                updated_task = task
            else:
                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = %s,
                        completed_at = CASE
                            WHEN %s = 'completed' THEN CURRENT_TIMESTAMP
                            ELSE NULL
                        END
                    WHERE task_id = %s
                    RETURNING *;
                    """,
                    (update.status, update.status, task_id),
                )
                updated_task = cursor.fetchone()

    return updated_task


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM tasks WHERE task_id = %s RETURNING *;",
                (task_id,),
            )
            deleted_task = cursor.fetchone()
            if deleted_task is None:
                raise HTTPException(status_code=404, detail="Task not found")

    return deleted_task


@app.put("/tasks/{task_id}/details")
def update_task_details(task_id: int, details: TaskCreate):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tasks
                SET task_type = %s,
                    recipient = %s,
                    description = %s
                WHERE task_id = %s
                RETURNING *;
                """,
                (details.task_type, details.recipient, details.description, task_id),
            )
            updated_task = cursor.fetchone()
            if updated_task is None:
                raise HTTPException(status_code=404, detail="Task not found")

    return updated_task


app.include_router(create_web_router(
    list_tasks=list_tasks,
    retrieve_task=retrieve_task,
    create_task=create_task,
    update_task_details=update_task_details,
    update_task_status=update_task_status,
    delete_task=delete_task,
))
