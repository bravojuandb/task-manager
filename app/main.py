from fastapi import FastAPI

from app.db import get_connection
from app.models import TaskCreate

app = FastAPI(title="k8 Task Manager")

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