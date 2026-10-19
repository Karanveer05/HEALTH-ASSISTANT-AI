"""Pydantic models: API input, and the structured JSON the LLM must return (validated before use)."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TIME = r"^([01]\d|2[0-3]):[0-5]\d$"


# ---------- API input ----------

class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    age: int = Field(ge=0, le=120)
    sex: Literal["male", "female", "other"]
    weight_kg: float | None = Field(default=None, ge=1, le=400)
    height_cm: float | None = Field(default=None, ge=30, le=250)
    conditions: list[str] = []
    allergies: list[str] = []
    medications: list[str] = []
    pregnant: bool = False
    smoker: bool = False
    alcohol: bool = False
    diet_preference: Literal["veg", "egg", "nonveg"] = "veg"
    region: Literal["north", "south", "any"] = "any"
    wake_time: str = Field(default="07:00", pattern=TIME)
    breakfast_time: str = Field(default="08:30", pattern=TIME)
    lunch_time: str = Field(default="13:30", pattern=TIME)
    snack_time: str = Field(default="17:30", pattern=TIME)
    dinner_time: str = Field(default="20:30", pattern=TIME)
    sleep_time: str = Field(default="22:30", pattern=TIME)
    emergency_contact_name: str = Field(default="", max_length=80)
    emergency_contact_phone: str = Field(default="", max_length=20)
    notes: str = Field(default="", max_length=1000)

    @field_validator("conditions", "allergies", "medications")
    @classmethod
    def _clean(cls, v):
        return [s.strip()[:100] for s in v if s and s.strip()][:30]

    @model_validator(mode="after")
    def _pregnancy_only_for_female(self):
        if self.sex != "female":
            self.pregnant = False
        return self


class CaseStart(BaseModel):
    complaint: str = Field(min_length=3, max_length=2000)
    duration: str = Field(default="", max_length=60)
    severity: int = Field(default=5, ge=1, le=10)
    other_symptoms: str = Field(default="", max_length=2000)


class AnswerIn(BaseModel):
    question: str = Field(max_length=500)
    answer: str = Field(max_length=1000)


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=5)


# ---------- LLM structured output ----------

class FollowUpQuestion(BaseModel):
    question: str
    why: str = ""
    type: Literal["text", "yes_no", "choice", "number"] = "text"
    options: list[str] = []


class FollowUpPlan(BaseModel):
    enough_info: bool
    questions: list[FollowUpQuestion] = Field(default_factory=list, max_length=3)
    need_report: bool = False
    suggested_tests: list[str] = []
    reason: str = ""


class ExtractedLab(BaseModel):
    name: str
    value: float
    unit: str = ""
    reference_range: str = ""


class LabExtraction(BaseModel):
    values: list[ExtractedLab] = []


class PossibleCondition(BaseModel):
    name: str
    matched_id: str | None = None
    confidence: Literal["low", "medium", "high"]
    reasoning: str
    supporting_findings: list[str] = []
    against_findings: list[str] = []
    reference_ids: list[str] = []


class ConditionAnalysis(BaseModel):
    summary: str
    conditions: list[PossibleCondition] = Field(max_length=5)
    contributing_factors: list[str] = []
    uncertainty_note: str


class SymptomSummary(BaseModel):
    key_symptoms: list[str]
    timeline: str = ""
    notable_negatives: list[str] = []
