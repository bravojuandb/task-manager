"""Order rules; opt in to PostgreSQL checks with K8_TEST_DATABASE=1.

Database checks use connection-local temporary tables and roll back all data.
"""
import asyncio
from contextlib import contextmanager
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.models import TaskCreate, TaskStatusUpdate


def order(**changes):
    values = dict(task_type="order", description="Synthetic order",
                  customer="Example customer", supplier="Example supplier")
    values.update(changes)
    return values


class OrderModelTests(unittest.TestCase):
    def test_contacts_available_across_task_types(self):
        for role in ('customer', 'supplier', 'other'):
            task = TaskCreate(task_type='email', description='Test', **{role: ' Example '})
            self.assertEqual(getattr(task, role), 'Example')
        for kind in ('email', 'phone_call', 'follow_up', 'quotation', 'price_request', 'other'):
            task = TaskCreate(task_type=kind, description='Test', customer='Customer', supplier='Supplier', other='Another')
            self.assertEqual(task.supplier, 'Supplier')
        for values in (
            dict(task_type='email'),
            dict(task_type='email', recipient='Removed field'),
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                TaskCreate(description='Test', **values)

    def test_requires_both_parties(self):
        for field in ("customer", "supplier"):
            for value in (None, "", " \t\n"):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    TaskCreate(**order(**{field: value}))

    def test_progress_rules(self):
        with self.assertRaises(ValidationError):
            TaskCreate(**order(order_delivered=True))
        for flags, status in (({}, "pending"), ({"order_placed": True}, "in_progress"),
                              ({"order_placed": True, "order_delivered": True}, "completed")):
            self.assertEqual(TaskCreate(**order(**flags)).order_status(), status)

    def test_price_request_and_wrong_party_fields(self):
        self.assertEqual(TaskCreate(task_type="price_request", supplier=" Supplier ", description="Prices").supplier, "Supplier")
        with self.assertRaises(ValidationError):
            TaskCreate(task_type="price_request", description="Prices")
        with self.assertRaises(ValidationError):
            TaskCreate(task_type="email", other="Example", description="Test", order_placed=True)
        with self.assertRaises(ValidationError):
            TaskCreate(**order(other="Invalid additional contact"))


@unittest.skipUnless(os.environ.get("K8_TEST_DATABASE") == "1", "Set K8_TEST_DATABASE=1 for temporary PostgreSQL tests")
class OrderDatabaseTests(unittest.TestCase):
    def setUp(self):
        from app.db import get_connection
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.root = Path(__file__).resolve().parents[1]
        self.conn.execute((self.root / 'sql/schema.sql').read_text().replace(
            'CREATE TABLE IF NOT EXISTS tasks', 'CREATE TEMP TABLE tasks', 1))

        @contextmanager
        def temporary_connection():
            with self.conn.transaction():
                yield self.conn
        self.patcher = patch('app.main.get_connection', temporary_connection)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_lifecycle_and_no_reopening(self):
        from app.main import create_task, update_task_details, update_task_status
        task = create_task(TaskCreate(**order()))
        self.assertEqual(task['status'], 'pending')
        task = update_task_details(task['task_id'], TaskCreate(**order(order_placed=True)))
        self.assertEqual(task['status'], 'in_progress')
        delivered = TaskCreate(**order(order_placed=True, order_delivered=True))
        task = update_task_details(task['task_id'], delivered)
        self.assertEqual(task['status'], 'completed')
        self.assertIsNotNone(task['completed_at'])
        self.assertEqual(update_task_details(task['task_id'], delivered)['completed_at'], task['completed_at'])
        with self.assertRaises(HTTPException) as exc:
            update_task_details(task['task_id'], TaskCreate(**order(order_placed=True)))
        self.assertEqual(exc.exception.status_code, 409)
        with self.assertRaises(HTTPException) as exc:
            update_task_status(task['task_id'], TaskStatusUpdate(status='pending'))
        self.assertEqual(exc.exception.status_code, 409)

    def test_multiple_contacts_persist_for_non_orders(self):
        from app.main import create_task, update_task_details, retrieve_task
        for kind in ('email', 'phone_call', 'follow_up', 'quotation', 'price_request', 'other'):
            task = create_task(TaskCreate(task_type=kind, description='Test',
                                         customer='Customer', supplier='Supplier', other='Other'))
            saved = retrieve_task(task['task_id'])
            self.assertEqual((saved['customer'], saved['supplier'], saved['other']),
                             ('Customer', 'Supplier', 'Other'))
            self.assertFalse(saved['order_placed'])
            self.assertFalse(saved['order_delivered'])
            updated = update_task_details(task['task_id'], TaskCreate(
                task_type=kind, description='Edited', customer='Customer', supplier='New supplier'))
            self.assertEqual(updated['supplier'], 'New supplier')
            self.assertIsNone(updated['other'])

    def test_created_at_sorting_and_status_filter(self):
        from app.main import create_task, list_tasks
        ids = []
        for day, status in ((2, 'pending'), (1, 'pending'), (2, 'pending'), (3, 'in_progress')):
            task = create_task(TaskCreate(task_type='email', other='Example', description='Sort test'))
            ids.append(task['task_id'])
            self.conn.execute("UPDATE tasks SET created_at = %s, status = %s WHERE task_id = %s",
                              (f'2026-01-{day:02d}T12:00:00+00:00', status, task['task_id']))
        expected = [ids[1], ids[0], ids[2], ids[3]]
        self.assertEqual([t['task_id'] for t in list_tasks()], expected)
        self.assertEqual([t['task_id'] for t in list_tasks(sort='newest')], list(reversed(expected)))
        self.assertEqual([t['task_id'] for t in list_tasks('pending')], expected[:-1])
        self.assertEqual([t['task_id'] for t in list_tasks('pending', sort='newest')], list(reversed(expected[:-1])))

    def test_database_constraints(self):
        import psycopg
        from app.main import create_task
        task = create_task(TaskCreate(**order()))
        for sql in (
            "UPDATE tasks SET order_delivered = TRUE",
            "UPDATE tasks SET customer = NULL",
            "UPDATE tasks SET supplier = '   '",
            "UPDATE tasks SET status = 'completed', completed_at = CURRENT_TIMESTAMP",
        ):
            with self.assertRaises(psycopg.IntegrityError):
                with self.conn.transaction():
                    self.conn.execute(sql)
        self.assertEqual(self.conn.execute('SELECT status FROM tasks').fetchone()['status'], task['status'])

    def test_reclassify_contact_without_changing_status(self):
        import psycopg
        from app.main import create_task, update_task_details, update_task_status
        task = create_task(TaskCreate(task_type='email', other='Example', description='Test'))
        task = update_task_status(task['task_id'], TaskStatusUpdate(status='completed'))
        edited = update_task_details(task['task_id'], TaskCreate(task_type='email', customer='Example', description='Edited'))
        self.assertEqual(edited['customer'], 'Example')
        self.assertIsNone(edited['other'])
        self.assertEqual(edited['status'], 'completed')
        self.assertEqual(edited['completed_at'], task['completed_at'])
        for sql in (
            "UPDATE tasks SET customer = NULL",
            "UPDATE tasks SET customer = '  '",
            "UPDATE tasks SET order_placed = TRUE",
        ):
            with self.assertRaises(psycopg.IntegrityError):
                with self.conn.transaction():
                    self.conn.execute(sql)

    def test_form_round_trip_and_price_request(self):
        from app.main import app
        from test_web import request
        async def flow():
            code, _, body = await request(app, '/ui/tasks/new', 'POST', order(order_placed='true', order_delivered='true'))
            self.assertEqual(code, 303)
            task = self.conn.execute('SELECT * FROM tasks').fetchone()
            self.assertEqual(task['status'], 'completed')
            code, _, body = await request(app, f"/ui/tasks/{task['task_id']}/edit")
            self.assertEqual(code, 200)
            self.assertIn('Example customer', body)
            self.assertIn('name="order_delivered" id="order_delivered" value="true" checked', body)
            code, _, body = await request(app, '/ui/tasks/new', 'POST', order(order_delivered='true'))
            self.assertEqual(code, 422)
            self.assertIn('Example supplier', body)
            code, _, _ = await request(app, '/ui/tasks/new', 'POST', dict(task_type='price_request', contact_type='supplier', supplier='Example', description='Price'))
            self.assertEqual(code, 303)
            self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM tasks').fetchone()['n'], 2)
        asyncio.run(flow())

    def test_legacy_migration_preserves_recipient(self):
        from app.main import update_task_details, app
        from test_web import request
        self.conn.execute('DROP TABLE pg_temp.tasks')
        self.conn.execute("""CREATE TEMP TABLE tasks (
            task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            task_type TEXT NOT NULL CONSTRAINT tasks_task_type_check CHECK (task_type IN ('order', 'email')),
            recipient TEXT NOT NULL, description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMPTZ)""")
        self.conn.execute('ALTER TABLE tasks DROP CONSTRAINT tasks_task_type_check')
        self.conn.execute("ALTER TABLE tasks ADD CONSTRAINT tasks_task_type_check CHECK (task_type IN ('order', 'email', 'quotation', 'price_request'))")
        for kind in ('email', 'quotation', 'price_request'):
            self.conn.execute("INSERT INTO tasks (task_type, recipient, description) VALUES (%s, 'Preserve this name', 'Synthetic')", (kind,))
        task = self.conn.execute("INSERT INTO tasks (task_type, recipient, description, status, completed_at) VALUES ('order', 'Keep original reference', 'Old order', 'completed', CURRENT_TIMESTAMP) RETURNING *").fetchone()
        self.conn.execute((self.root / 'sql/002_order_details.sql').read_text())
        migrated = self.conn.execute('SELECT * FROM tasks WHERE task_id = %s', (task['task_id'],)).fetchone()
        self.assertEqual(migrated['recipient'], task['recipient'])
        self.assertEqual(migrated['completed_at'], task['completed_at'])
        self.conn.execute((self.root / 'sql/003_contact_roles.sql').read_text())
        self.conn.execute((self.root / 'sql/004_flexible_contacts.sql').read_text())
        for kind, field in (('email', 'other'), ('quotation', 'customer'), ('price_request', 'supplier')):
            mapped = self.conn.execute('SELECT * FROM tasks WHERE task_type = %s', (kind,)).fetchone()
            self.assertEqual(mapped[field], 'Preserve this name')
            self.assertNotIn('recipient', mapped)
        self.assertIn('Keep original reference', asyncio.run(request(app, f"/ui/tasks/{task['task_id']}/edit"))[2])
        updated = update_task_details(task['task_id'], TaskCreate(**order(order_placed=True, order_delivered=True)))
        self.assertIsNone(updated['other'])
        self.assertNotIn('recipient', updated)
        self.assertEqual(updated['completed_at'], task['completed_at'])
        self.conn.execute('ALTER TABLE tasks VALIDATE CONSTRAINT tasks_parties_consistent')
        self.conn.execute('ALTER TABLE tasks VALIDATE CONSTRAINT tasks_order_progress_consistent')
