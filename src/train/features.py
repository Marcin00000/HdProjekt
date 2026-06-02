"""Przygotowanie cech pod model XGBoost (Pipeline sklearn)."""

from __future__ import annotations

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

TARGET = "salary"

CATEGORICAL_FEATURES = [
    "job_title",
    "education_level",
    "industry",
    "company_size",
    "location",
    "remote_work",
]

NUMERIC_FEATURES = [
    "experience_years",
    "skills_count",
    "certifications",
    "edu_ord",
    "exp_sq",
    "exp_x_skills",
]

RAW_FEATURE_COLUMNS = [
    "job_title",
    "experience_years",
    "education_level",
    "skills_count",
    "industry",
    "company_size",
    "location",
    "remote_work",
    "certifications",
]

EDUCATION_ORDER = {
    "High School": 0,
    "Associate": 1,
    "Bachelor": 2,
    "Master": 3,
    "PhD": 4,
    "MBA": 5,
}


class FeatureEngineer(BaseEstimator, TransformerMixin):
    """Cechy pochodne (liczone w pipeline — bez globalnego wycieku z silver)."""

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        out["edu_ord"] = out["education_level"].map(EDUCATION_ORDER).fillna(2).astype(float)
        exp = out["experience_years"].astype(float)
        skills = out["skills_count"].astype(float)
        out["exp_sq"] = exp**2
        out["exp_x_skills"] = exp * skills
        return out[CATEGORICAL_FEATURES + NUMERIC_FEATURES]


def build_preprocessor() -> Pipeline:
    return Pipeline(
        [
            ("engineer", FeatureEngineer()),
            (
                "encode",
                ColumnTransformer(
                    transformers=[
                        (
                            "cat",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                            CATEGORICAL_FEATURES,
                        ),
                        ("num", "passthrough", NUMERIC_FEATURES),
                    ],
                ),
            ),
        ]
    )


def prepare_train_test(
    df: pd.DataFrame,
    test_size: float = 0.2,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    missing = set(RAW_FEATURE_COLUMNS + [TARGET]) - set(df.columns)
    if missing:
        raise ValueError(f"Brak kolumn w silver: {missing}")

    X = df[RAW_FEATURE_COLUMNS]
    y = df[TARGET]
    return train_test_split(X, y, test_size=test_size, random_state=random_state)
