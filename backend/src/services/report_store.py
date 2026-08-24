"""Local persistent storage for completed audit reports."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

REPORTS_DIR = Path("backend/cache/reports")


def _report_path(job_id: str) -> Path:
    safe_job_id = "".join(character for character in job_id if character.isalnum() or character == "-")
    if not safe_job_id:
        raise ValueError("Invalid report ID")
    return REPORTS_DIR / f"{safe_job_id}.json"


def save_report(job_id: str, report: Dict[str, Any]) -> None:
    """Persist a report using an atomic file replacement."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _report_path(job_id)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=REPORTS_DIR, delete=False
    ) as temporary_file:
        json.dump(report, temporary_file, indent=2)
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, report_path)


def get_report(job_id: str) -> Optional[Dict[str, Any]]:
    """Load a persisted report, or return None when it does not exist."""
    report_path = _report_path(job_id)
    if not report_path.exists():
        return None
    try:
        with report_path.open("r", encoding="utf-8") as report_file:
            return json.load(report_file)
    except (OSError, json.JSONDecodeError):
        return None


def list_reports() -> List[Dict[str, Any]]:
    """Return persisted reports ordered from newest to oldest."""
    if not REPORTS_DIR.exists():
        return []
    reports: List[Dict[str, Any]] = []
    for report_path in REPORTS_DIR.glob("*.json"):
        report = get_report(report_path.stem)
        if report is not None:
            reports.append(report)
    return sorted(reports, key=lambda report: report.get("completed_at", ""), reverse=True)


def delete_report(job_id: str) -> bool:
    """Delete a persisted report and indicate whether it existed."""
    report_path = _report_path(job_id)
    try:
        report_path.unlink()
        return True
    except FileNotFoundError:
        return False
