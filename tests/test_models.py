import unittest

from pydantic import ValidationError

from app.models import TaskCreate


class TaskCreateTests(unittest.TestCase):
    def test_rejects_blank_and_missing_text(self):
        for field in ("customer", "description"):
            for value in (None, "", "   ", "\t\n\r "):
                with self.subTest(field=field, value=value):
                    data = dict(task_type="email", customer="Example", description="Test")
                    data[field] = value
                    with self.assertRaises(ValidationError):
                        TaskCreate(**data)
            data = dict(task_type="email", customer="Example", description="Test")
            del data[field]
            with self.assertRaises(ValidationError):
                TaskCreate(**data)

    def test_strips_surrounding_whitespace(self):
        task = TaskCreate(
            task_type="quotation",
            customer=" \tExample supplier\n",
            description="\nRequest a quotation  ",
        )
        self.assertEqual(task.customer, "Example supplier")
        self.assertEqual(task.description, "Request a quotation")

    def test_rejects_unknown_task_type(self):
        with self.assertRaises(ValidationError):
            TaskCreate(task_type="invalid", customer="Example", description="Test")
