from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator


RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: Literal["email", "phone_call", "order", "follow_up", "quotation", "price_request", "other"]
    description: RequiredText
    customer: RequiredText | None = None
    supplier: RequiredText | None = None
    other: RequiredText | None = None
    order_placed: bool = False
    order_delivered: bool = False

    @model_validator(mode="after")
    def validate_parties_and_order(self):
        if self.task_type == "order":
            if self.customer is None or self.supplier is None:
                raise ValueError("Orders require both a customer and a supplier.")
            if self.other is not None:
                raise ValueError("Orders use customer and supplier, not other contacts.")
            if self.order_delivered and not self.order_placed:
                raise ValueError("An order must be placed before it can be delivered.")
        else:
            if not any(value is not None for value in (self.customer, self.supplier, self.other)):
                raise ValueError("Enter at least one contact: customer, supplier or other.")
            if self.order_placed or self.order_delivered:
                raise ValueError("Order fields are only available for orders.")
        return self

    def order_status(self):
        return "completed" if self.order_delivered else "in_progress" if self.order_placed else "pending"


class TaskStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "in_progress", "completed"]
