"""HTML form routes that reuse the application's existing task operations."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.models import TaskCreate, TaskStatusUpdate


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
TASK_TYPES = ("email", "phone_call", "order", "follow_up", "quotation", "other")
STATUSES = ("pending", "in_progress", "completed")
StatusFilter = Literal["", "pending", "in_progress", "completed"]


def create_web_router(
    list_tasks, retrieve_task, create_task, update_task_details,
    update_task_status, delete_task,
):
    router = APIRouter(include_in_schema=False)

    def redirect(status=""):
        return RedirectResponse("/" + ("?" + urlencode({"status": status}) if status else ""), status_code=303)

    def task_list(request, status="", error=None, code=200):
        return templates.TemplateResponse(
            request=request, name="tasks.html",
            context={"tasks": list_tasks(status or None), "selected_status": status,
                     "statuses": STATUSES, "error": error}, status_code=code,
        )

    def task_form(request, values, task_id=None, errors=None, code=200):
        return templates.TemplateResponse(
            request=request, name="task_form.html",
            context={"values": values, "task_id": task_id,
                     "task_types": TASK_TYPES, "errors": errors or {}}, status_code=code,
        )

    @router.get("/")
    def home(request: Request, status: StatusFilter = ""):
        return task_list(request, status)

    @router.get("/ui/tasks/new")
    def new_task(request: Request):
        return task_form(request, {"task_type": "email", "recipient": "", "description": ""})

    @router.get("/ui/tasks/{task_id}/edit")
    def edit_task(request: Request, task_id: int):
        try:
            return task_form(request, retrieve_task(task_id), task_id)
        except HTTPException as exc:
            return task_list(request, error=exc.detail, code=exc.status_code)

    def save(request, values, task_id=None):
        try:
            details = TaskCreate(**values)
        except ValidationError as exc:
            errors = {str(e["loc"][0]): e["msg"] for e in exc.errors()}
            return task_form(request, values, task_id, errors, 422)
        try:
            if task_id is None:
                create_task(details)
            else:
                update_task_details(task_id, details)
        except HTTPException as exc:
            return task_form(request, values, task_id, {"form": exc.detail}, exc.status_code)
        return redirect()

    @router.post("/ui/tasks/new")
    def submit_new(request: Request, task_type: str = Form(""),
                   recipient: str = Form(""), description: str = Form("")):
        return save(request, dict(task_type=task_type, recipient=recipient, description=description))

    @router.post("/ui/tasks/{task_id}/edit")
    def submit_edit(request: Request, task_id: int, task_type: str = Form(""),
                    recipient: str = Form(""), description: str = Form("")):
        return save(request, dict(task_type=task_type, recipient=recipient, description=description), task_id)

    @router.post("/ui/tasks/{task_id}/status")
    def submit_status(request: Request, task_id: int, status: str = Form(""),
                      filter_status: StatusFilter = Form("")):
        try:
            update = TaskStatusUpdate(status=status)
        except ValidationError:
            return task_list(request, filter_status, "Choose a valid task status.", 422)
        try:
            update_task_status(task_id, update)
        except HTTPException as exc:
            return task_list(request, filter_status, exc.detail, exc.status_code)
        return redirect(filter_status)

    @router.post("/ui/tasks/{task_id}/delete")
    def submit_delete(request: Request, task_id: int, confirm: str = Form(""),
                      filter_status: StatusFilter = Form("")):
        if confirm != "yes":
            return task_list(request, filter_status, "Confirm deletion before removing a task.", 422)
        try:
            delete_task(task_id)
        except HTTPException as exc:
            return task_list(request, filter_status, exc.detail, exc.status_code)
        return redirect(filter_status)

    return router
