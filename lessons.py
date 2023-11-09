import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, PositiveInt


class Course(BaseModel):
    name: str
    lessons: List[int]
    happened_weeks: List[int]
    classroom: Optional[str] = Field(default="undefined")
    teacher: Optional[str] = Field(default="undefined")
    description: Optional[str] = Field(default="undefined")

    @property
    def label(self) -> str:
        return f"[{self.name}] At {self.classroom}\n--------------\n{self.teacher}\n{self.description}"


class SchedulerConfig(BaseModel):
    class Config:
        allow_mutation = False
        validate_assignment = True

    lessons_index_count: int = 13
    term_weeks_count: int = 20
    morning_lessons_count: PositiveInt = Field(default=5)
    afternoon_lessons_count: PositiveInt = Field(default=5)
    evening_lessons_count: PositiveInt = Field(default=4)


class ScheduleFrame(BaseModel):
    config: SchedulerConfig = Field(default_factory=SchedulerConfig)
    start_day: datetime.datetime


class Schedule(BaseModel):
    courses: List[Course]
