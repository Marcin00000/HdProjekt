"""Schematy Pydantic — wejscie/wyjscie API prognozy pensji."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.train.features import EDUCATION_ORDER


class SalaryPredictRequest(BaseModel):
    job_title: str = Field(..., examples=["Data Scientist"])
    experience_years: int = Field(..., ge=0, le=40, examples=[5])
    education_level: str = Field(..., examples=["Master"])
    skills_count: int = Field(..., ge=0, examples=[10])
    industry: str = Field(..., examples=["Technology"])
    company_size: str = Field(..., examples=["Medium"])
    location: str = Field(..., examples=["USA"])
    remote_work: str = Field(..., examples=["Yes"])
    certifications: int = Field(..., ge=0, examples=[2])

    @field_validator(
        "job_title",
        "education_level",
        "industry",
        "company_size",
        "location",
        "remote_work",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("education_level")
    @classmethod
    def normalize_education(cls, v: str) -> str:
        for key in EDUCATION_ORDER:
            if key.lower() == v.lower():
                return key
        return v

    @field_validator("remote_work")
    @classmethod
    def normalize_remote(cls, v: str) -> str:
        mapping = {"yes": "Yes", "no": "No", "hybrid": "Hybrid"}
        return mapping.get(v.lower(), v)


class SalaryPredictResponse(BaseModel):
    predicted_salary: float = Field(..., description="Prognozowana pensja roczna (USD)")
    currency: str = "USD"
    warning: str | None = Field(
        None,
        description="Ostrzezenie gdy wartosci kategorii nie wystepuja w danych treningowych",
    )


class HealthResponse(BaseModel):
    status: str = "ok"
    model_loaded: bool
