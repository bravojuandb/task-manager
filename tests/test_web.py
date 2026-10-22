"""Exercise HTTP form behavior without writing to the application database."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.web import create_web_router


async def request(app, path, method="GET", data=None):
    """Send an HTTP request through ASGI without an extra test dependency."""
    path, _, query = path.partition("?")
    body = urlencode(data or {}).encode()
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "scheme": "http", "method": method, "path": path, "raw_path": path.encode(),
        "query_string": query.encode(), "root_path": "",
        "headers": [(b"host", b"testserver"),
                    (b"content-type", b"application/x-www-form-urlencoded")],
        "server": ("testserver", 80), "client": ("127.0.0.1", 12345),
    }, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), content.decode()


class WebTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.task = dict(task_id=1, task_type="email", other="<script>Example</script>",
                         description="First line\nSecond line", status="pending",
                         created_at=datetime.now(timezone.utc), completed_at=None)
        self.operations = {name: Mock() for name in (
            "list_tasks", "retrieve_task", "create_task", "update_task_details",
            "update_task_status", "delete_task",
        )}
        self.operations["list_tasks"].return_value = [self.task]
        self.operations["retrieve_task"].return_value = self.task
        self.app = FastAPI()
        self.app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parents[1] / "app/static"), name="static")
        self.app.include_router(create_web_router(**self.operations))

    async def test_list_filter_and_escaping(self):
        code, _, body = await request(self.app, "/?status=pending")
        self.assertEqual(code, 200)
        self.operations["list_tasks"].assert_called_with("pending", sort="oldest")
        self.assertIn("&lt;script&gt;Example&lt;/script&gt;", body)
        self.assertNotIn("<script>Example</script>", body)
        self.assertEqual((await request(self.app, "/?status=invalid"))[0], 422)

    async def test_create_validation_and_redirect(self):
        data = dict(task_type="email", contact_type="other", other="   ", description="Keep this text")
        code, _, body = await request(self.app, "/ui/tasks/new", "POST", data)
        self.assertEqual(code, 422)
        self.assertIn("Keep this text", body)
        self.operations["create_task"].assert_not_called()
        data["other"] = " Example "
        code, headers, _ = await request(self.app, "/ui/tasks/new", "POST", data)
        self.assertEqual(code, 303)
        self.assertEqual(headers[b"location"], b"/")
        self.assertEqual(self.operations["create_task"].call_args.args[0].other, "Example")

    async def test_edit_and_missing_task(self):
        self.assertEqual((await request(self.app, "/ui/tasks/1/edit"))[0], 200)
        code, _, _ = await request(self.app, "/ui/tasks/1/edit", "POST",
                                  dict(task_type="other", contact_type="other", other="Example", description="Revised"))
        self.assertEqual(code, 303)
        self.assertEqual(self.operations["update_task_details"].call_args.args[0], 1)
        self.operations["retrieve_task"].side_effect = HTTPException(404, "Task not found")
        code, _, body = await request(self.app, "/ui/tasks/99/edit")
        self.assertEqual(code, 404)
        self.assertIn("Task not found", body)

    async def test_status_conflict_and_filter_preservation(self):
        data = dict(status="completed", filter_status="pending")
        code, headers, _ = await request(self.app, "/ui/tasks/1/status", "POST", data)
        self.assertEqual(code, 303)
        self.assertEqual(headers[b"location"], b"/?status=pending")
        self.operations["update_task_status"].side_effect = HTTPException(409, "Completed tasks cannot be reopened")
        code, _, body = await request(self.app, "/ui/tasks/1/status", "POST", dict(status="pending"))
        self.assertEqual(code, 409)
        self.assertIn("Completed tasks cannot be reopened", body)

    async def test_delete_requires_confirmation(self):
        code, _, _ = await request(self.app, "/ui/tasks/1/delete", "POST")
        self.assertEqual(code, 422)
        self.operations["delete_task"].assert_not_called()
        code, _, _ = await request(self.app, "/ui/tasks/1/delete", "POST", dict(confirm="yes"))
        self.assertEqual(code, 303)
        self.operations["delete_task"].assert_called_once_with(1)

    async def test_empty_and_completed_states(self):
        self.task["status"] = "completed"
        self.task["completed_at"] = self.task["created_at"]
        code, _, body = await request(self.app, "/")
        self.assertEqual(code, 200)
        self.assertNotIn('name="status" value="in_progress"', body.split('<section')[1])
        self.assertNotIn('name="status" value="pending"', body.split('<section')[1])
        self.operations["list_tasks"].return_value = []
        self.assertIn("No tasks yet", (await request(self.app, "/?status="))[2])
        self.assertIn("No matching tasks", (await request(self.app, "/"))[2])
        self.assertIn("No matching tasks", (await request(self.app, "/?status=completed"))[2])

    async def test_contacts_visible_and_multiple_values_preserved(self):
        from html.parser import HTMLParser
        class Fields(HTMLParser):
            def __init__(self):
                super().__init__()
                self.fields = {}
            def handle_starttag(self, tag, attrs):
                if tag == 'fieldset':
                    attrs = dict(attrs)
                    self.fields[attrs.get('id')] = attrs
        for kind in ('email', 'phone_call', 'order', 'follow_up', 'quotation', 'price_request', 'other'):
            self.task['task_type'] = kind
            page = (await request(self.app, '/ui/tasks/1/edit'))[2]
            fields = Fields()
            fields.feed(page)
            for role in ('customer', 'supplier'):
                self.assertNotIn('hidden', fields.fields[role + '-fields'])
                self.assertNotIn('disabled', fields.fields[role + '-fields'])
            self.assertEqual('hidden' in fields.fields['order-fields'], kind != 'order')
            data = dict(task_type=kind, description='Test', customer=' Customer ', supplier=' Supplier ')
            self.assertEqual((await request(self.app, '/ui/tasks/new', 'POST', data))[0], 303)
            saved = self.operations['create_task'].call_args.args[0]
            self.assertEqual(saved.customer, 'Customer')
            self.assertEqual(saved.supplier, 'Supplier')
        self.assertNotIn('name="recipient"', page)
        self.assertNotIn('name="contact_type"', page)
        self.operations['create_task'].reset_mock()
        self.assertEqual((await request(self.app, '/ui/tasks/new', 'POST',
                         dict(task_type='email', customer=' ', supplier='', other=' ', description='Test')))[0], 422)
        self.operations['create_task'].assert_not_called()

    async def test_sort_selection_and_redirects(self):
        code, _, body = await request(self.app, '/?status=pending&sort=newest')
        self.assertEqual(code, 200)
        self.operations['list_tasks'].assert_called_with('pending', sort='newest')
        self.assertIn('value="newest" selected', body)
        self.assertEqual((await request(self.app, '/?sort=invalid'))[0], 422)
        data = dict(status='completed', filter_status='pending', sort='newest')
        for action in ('status', 'delete'):
            data['confirm'] = 'yes'
            code, headers, _ = await request(self.app, '/ui/tasks/1/' + action, 'POST', data)
            self.assertEqual(code, 303)
            self.assertEqual(headers[b'location'], b'/?status=pending&sort=newest')

    async def test_default_pending_and_explicit_all_statuses(self):
        code, _, body = await request(self.app, '/')
        self.assertEqual(code, 200)
        self.operations['list_tasks'].assert_called_with('pending', sort='oldest')
        self.assertIn('value="pending" selected', body)
        await request(self.app, '/?status=')
        self.operations['list_tasks'].assert_called_with(None, sort='oldest')
        for action in ('status', 'delete'):
            code, headers, _ = await request(self.app, '/ui/tasks/1/' + action, 'POST',
                dict(status='completed', confirm='yes', filter_status='', sort='newest'))
            self.assertEqual(code, 303)
            self.assertEqual(headers[b'location'], b'/?status=&sort=newest')
        self.operations['list_tasks'].return_value = []
        body = (await request(self.app, '/'))[2]
        self.assertIn('/?status=&amp;sort=oldest', body)
