from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: Literal["email", "phone_call", "order", "follow_up", "quotation", "other"]
    recipient: RequiredText
    description: RequiredText
