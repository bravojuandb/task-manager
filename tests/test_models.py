import unittest

from pydantic import ValidationError

from app.models import TaskCreate


class TaskCreateTests(unittest.TestCase):
    def test_rejects_blank_and_missing_text(self):
        for field in ("recipient", "description"):
            for value in (None, "", "   ", "\t\n\r "):
                with self.subTest(field=field, value=value):
                    data = dict(task_type="email", recipient="Example", description="Test")
                    data[field] = value
                    with self.assertRaises(ValidationError):
                        TaskCreate(**data)
            data = dict(task_type="email", recipient="Example", description="Test")
            del data[field]
            with self.assertRaises(ValidationError):
                TaskCreate(**data)

    def test_strips_surrounding_whitespace(self):
        task = TaskCreate(
            task_type="quotation",
            recipient=" \tExample supplier\n",
            description="\nRequest a quotation  ",
        )
        self.assertEqual(task.recipient, "Example supplier")
        self.assertEqual(task.description, "Request a quotation")

    def test_rejects_unknown_task_type(self):
        with self.assertRaises(ValidationError):
            TaskCreate(task_type="invalid", recipient="Example", description="Test")
