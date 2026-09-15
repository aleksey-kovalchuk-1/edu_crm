from datetime import date
from typing import Annotated
from pydantic import BaseModel, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

class LaunchInput(BaseModel):
    university_id: int = Field(gt=0)
    program: Text
    product: Text
    owner: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    students: int = Field(ge=0, le=100000)
    deadline: date

class StageInput(BaseModel):
    stage: int = Field(ge=0, le=12)

class TaskInput(BaseModel):
    done: bool
