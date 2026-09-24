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
    it_product_id: int | None = Field(default=None, gt=0)

class LaunchProductInput(BaseModel):
    it_product_id: int | None = Field(default=None, gt=0)

class StageInput(BaseModel):
    stage: int = Field(ge=0, le=12)
