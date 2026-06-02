"""Eksploracyjna analiza danych — statystyki i wykresy (zapis do reports/eda/)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT

REPORT_DIR = PROJECT_ROOT / "reports" / "eda"


def run_eda(df: pd.DataFrame, label: str = "raw") -> Path:
    """Generuje raport tekstowy + JSON podsumowania; opcjonalnie wykresy PNG."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    summary = {
        "label": label,
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "null_counts": df.isnull().sum().to_dict(),
        "numeric_describe": df.describe().to_dict() if df.select_dtypes("number").shape[1] else {},
        "salary_by_location_top10": (
            df.groupby("location")["salary"].median().sort_values(ascending=False).head(10).to_dict()
            if "salary" in df.columns and "location" in df.columns
            else {}
        ),
        "job_title_counts_top10": (
            df["job_title"].value_counts().head(10).to_dict() if "job_title" in df.columns else {}
        ),
    }

    json_path = REPORT_DIR / f"summary_{label}.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# EDA — {label}",
        f"",
        f"- Wierszy: **{summary['rows']}**",
        f"- Kolumn: **{len(summary['columns'])}**",
        f"",
        "## Braki danych",
        "```json",
        json.dumps(summary["null_counts"], indent=2),
        "```",
        "",
        "## Top 10 lokalizacji (mediana salary)",
        "```json",
        json.dumps(summary["salary_by_location_top10"], indent=2),
        "```",
    ]
    md_path = REPORT_DIR / f"report_{label}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    _save_plots(df, label)
    return md_path


def _save_plots(df: pd.DataFrame, label: str) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    if "salary" not in df.columns:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    axes[0].hist(df["salary"], bins=50, edgecolor="black", alpha=0.7)
    axes[0].set_title("Rozkład wynagrodzenia")
    axes[0].set_xlabel("salary")

    if "experience_years" in df.columns:
        axes[1].scatter(df["experience_years"], df["salary"], alpha=0.15, s=5)
        axes[1].set_title("Salary vs doświadczenie")
        axes[1].set_xlabel("experience_years")

    fig.tight_layout()
    fig.savefig(REPORT_DIR / f"plots_{label}.png", dpi=120)
    plt.close(fig)
