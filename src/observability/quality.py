from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


_SUMMARY_MIN_CHARS = 80


def _blank_mask(series: pd.Series) -> pd.Series:
    """Treat null, empty and whitespace-only cells as missing."""
    return series.isna() | series.astype("string").str.strip().eq("").fillna(True)


def _check(name: str, dimension: str, passed: bool, observed: Any, expected: str) -> dict[str, Any]:
    return {
        "name": name,
        "dimension": dimension,
        "passed": bool(passed),
        "observed": observed,
        "expected": expected,
    }


def _freshness_inputs(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Read freshness inputs already materialized by the cleaning step."""
    if "published" not in df.columns:
        dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    else:
        dates = pd.to_datetime(df["published"], errors="coerce", utc=True)

    if "age_days" not in df.columns:
        ages = pd.Series(float("nan"), index=df.index, dtype="float64")
    else:
        ages = pd.to_numeric(df["age_days"], errors="coerce")
    return dates, ages


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Measure completeness, uniqueness, validity, and freshness signals."""
    row_count = int(len(df))
    # max_results is an API upper bound, not a promise that Crossref will
    # return that many valid rows. Four complete rows are the operational
    # minimum needed by build_test_set; the exact count remains a signal for
    # before/after comparisons.
    expected_rows = min(4, max(1, int(settings.max_results)))

    paper_id_missing = row_count if "paper_id" not in df else int(_blank_mask(df["paper_id"]).sum())
    title_missing = row_count if "title" not in df else int(_blank_mask(df["title"]).sum())
    summary_missing = row_count if "summary" not in df else int(_blank_mask(df["summary"]).sum())

    if "paper_id" in df:
        normalized_ids = df["paper_id"].astype("string").str.strip().str.lower()
        valid_ids = normalized_ids[~_blank_mask(df["paper_id"])]
        duplicate_rows = int(valid_ids.duplicated(keep=False).sum())
        duplicate_extra_rows = int(valid_ids.duplicated(keep="first").sum())
    else:
        duplicate_rows = duplicate_extra_rows = 0

    duplicate_key_columns = [
        column for column in ("paper_id", "title", "summary", "published") if column in df.columns
    ]
    if duplicate_key_columns:
        duplicate_record_rows = int(
            df[duplicate_key_columns].astype("string").duplicated(keep=False).sum()
        )
        duplicate_record_extra_rows = int(
            df[duplicate_key_columns].astype("string").duplicated(keep="first").sum()
        )
    else:
        duplicate_record_rows = duplicate_record_extra_rows = 0

    if "summary" in df:
        summary_lengths = df["summary"].fillna("").astype(str).str.strip().str.len()
        short_summary_rows = int((summary_lengths < _SUMMARY_MIN_CHARS).sum())
    else:
        short_summary_rows = row_count

    if "age_days" in df:
        age_days = pd.to_numeric(df["age_days"], errors="coerce")
        null_age_days = int(age_days.isna().sum())
        invalid_age_mask = (age_days < 0).fillna(False) | age_days.isin(
            [float("inf"), float("-inf")]
        )
        invalid_age_days = int(invalid_age_mask.sum())
        stale_rows = int((age_days > settings.freshness_threshold_days).fillna(False).sum())
        finite_age_days = age_days[~age_days.isin([float("inf"), float("-inf")])]
        max_age_days = int(finite_age_days.max()) if finite_age_days.notna().any() else None
    else:
        null_age_days = row_count
        invalid_age_days = stale_rows = 0
        max_age_days = None

    checks = [
        _check("row_count", "volume", row_count >= expected_rows, row_count, f">= {expected_rows}"),
        _check("paper_id_not_null", "completeness", paper_id_missing == 0, paper_id_missing, "0 missing rows"),
        _check("paper_id_unique", "uniqueness", duplicate_extra_rows == 0, duplicate_rows, "0 duplicate rows"),
        _check(
            "records_unique",
            "uniqueness",
            duplicate_record_extra_rows == 0,
            duplicate_record_rows,
            "0 duplicate records",
        ),
        _check("title_not_null", "completeness", title_missing == 0, title_missing, "0 missing rows"),
        _check("summary_not_null", "completeness", summary_missing == 0, summary_missing, "0 missing rows"),
        _check(
            "summary_min_length",
            "validity",
            short_summary_rows == 0,
            short_summary_rows,
            f"0 rows shorter than {_SUMMARY_MIN_CHARS} characters",
        ),
        _check("age_days_not_null", "completeness", null_age_days == 0, null_age_days, "0 missing rows"),
        _check("age_days_valid", "validity", invalid_age_days == 0, invalid_age_days, "0 negative ages"),
        _check(
            "age_days_fresh",
            "freshness",
            stale_rows == 0,
            stale_rows,
            f"0 rows older than {settings.freshness_threshold_days} days",
        ),
    ]
    failed_checks = [item["name"] for item in checks if not item["passed"]]
    generated_at = datetime.now(UTC).isoformat()
    payload = {
        "report_name": report_name,
        "generated_at": generated_at,
        "passed": not failed_checks,
        "success": not failed_checks,
        "status": "pass" if not failed_checks else "fail",
        "total_rows": row_count,
        "failed_checks": failed_checks,
        "check_summary": {
            "total": len(checks),
            "passed": len(checks) - len(failed_checks),
            "failed": len(failed_checks),
        },
        "signals": {
            "row_count": row_count,
            "expected_min_rows": expected_rows,
            "requested_max_results": int(settings.max_results),
            "null_paper_id_rows": paper_id_missing,
            "null_title_rows": title_missing,
            "null_summary_rows": summary_missing,
            "duplicate_paper_id_rows": duplicate_rows,
            "duplicate_extra_rows": duplicate_extra_rows,
            "duplicate_record_rows": duplicate_record_rows,
            "duplicate_record_extra_rows": duplicate_record_extra_rows,
            "short_summary_rows": short_summary_rows,
            "null_age_days_rows": null_age_days,
            "invalid_age_days_rows": invalid_age_days,
            "stale_rows": stale_rows,
            "max_age_days": max_age_days,
            "freshness_threshold_days": settings.freshness_threshold_days,
            "age_days_source": "clean age_days derived from Crossref published timestamp",
        },
        "checks": checks,
    }
    report_path = settings.paths.quality_dir / f"{report_name}.json"
    write_json(report_path, payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build freshness evidence from cleaned ``published``/``age_days`` inputs."""
    measured_at = pd.Timestamp.now(tz="UTC")
    published, age_days = _freshness_inputs(df)
    valid_dates = published.dropna()
    invalid_timestamp_rows = int(published.isna().sum())
    missing_age_days_rows = int(age_days.isna().sum())
    non_finite_age_days_rows = int(age_days.isin([float("inf"), float("-inf")]).sum())
    negative_age_days_rows = int((age_days < 0).fillna(False).sum())
    stale_rows = int((age_days > settings.freshness_threshold_days).fillna(False).sum())
    total_rows = int(len(df))
    finite_age_days = age_days[~age_days.isin([float("inf"), float("-inf")])]

    def date_string(value: pd.Timestamp | None) -> str | None:
        return value.date().isoformat() if value is not None and not pd.isna(value) else None

    latest = valid_dates.max() if not valid_dates.empty else None
    oldest = valid_dates.min() if not valid_dates.empty else None
    payload = {
        "generated_at": measured_at.isoformat(),
        "timestamp_source": "cleaned published field sourced from Crossref",
        "age_days_source": "cleaned age_days field materialized during cleaning",
        "freshness_basis": "published supplies date bounds; age_days is compared with the threshold",
        "observation_clock": "UTC",
        "freshness_threshold_days": settings.freshness_threshold_days,
        "latest_published": date_string(latest),
        "oldest_published": date_string(oldest),
        "stale_rows": stale_rows,
        "invalid_timestamp_rows": invalid_timestamp_rows,
        "missing_age_days_rows": missing_age_days_rows,
        "non_finite_age_days_rows": non_finite_age_days_rows,
        "negative_age_days_rows": negative_age_days_rows,
        # Backwards-compatible alias used by existing report rendering.
        "future_timestamp_rows": negative_age_days_rows,
        "total_rows": total_rows,
        "min_age_days": int(finite_age_days.min()) if finite_age_days.notna().any() else None,
        "max_age_days": int(finite_age_days.max()) if finite_age_days.notna().any() else None,
        "mean_age_days": round(float(finite_age_days.mean()), 2) if finite_age_days.notna().any() else None,
        "is_fresh": bool(
            total_rows > 0
            and stale_rows == 0
            and invalid_timestamp_rows == 0
            and missing_age_days_rows == 0
            and non_finite_age_days_rows == 0
            and negative_age_days_rows == 0
        ),
    }
    write_json(Path(report_path), payload)
    return payload
