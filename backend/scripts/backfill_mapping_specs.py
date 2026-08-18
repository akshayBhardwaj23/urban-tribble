#!/usr/bin/env python3
"""Backfill mapping_spec_json for existing datasets and report role divergence.

Usage (from backend/):
  python -m scripts.backfill_mapping_specs
  python -m scripts.backfill_mapping_specs --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as module from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.models import Dataset, Upload  # noqa: E402
from services.cleaned_parquet import CleanedDataMissingError, ensure_cleaned_parquet  # noqa: E402
from services.column_detector import ColumnDetector  # noqa: E402
from services.column_profile import build_mapping_spec  # noqa: E402
from services.file_processor import FileProcessor  # noqa: E402
from services.ingest_pipeline import process_dataframe  # noqa: E402
from services.source_files import init_source_file, parse_source_files  # noqa: E402


def _old_roles(schema: dict) -> dict[str, str]:
    roles: dict[str, str] = {}
    for c in schema.get("date_columns") or []:
        roles[str(c)] = "timeline"
    for c in schema.get("revenue_columns") or []:
        roles[str(c)] = "amount_inflow"
    for c in schema.get("category_columns") or []:
        roles.setdefault(str(c), "dimension")
    for c in schema.get("numeric_columns") or []:
        roles.setdefault(str(c), "quantity")
    for c in schema.get("text_columns") or []:
        roles.setdefault(str(c), "text")
    return roles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report divergence without writing mapping_spec_json",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Run advisory LLM labelling during backfill (slower, costs tokens)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    detector = ColumnDetector()
    reader = FileProcessor()
    divergence: list[dict] = []
    updated = 0
    skipped = 0
    errors = 0

    try:
        datasets = db.query(Dataset).all()
        for ds in datasets:
            upload = db.query(Upload).filter(Upload.id == ds.upload_id).first()
            if not upload:
                skipped += 1
                continue

            old_schema = {}
            if ds.schema_json:
                try:
                    old_schema = json.loads(ds.schema_json)
                except (json.JSONDecodeError, TypeError):
                    old_schema = {}
            old = _old_roles(old_schema)

            # Ensure source_files_json exists for legacy uploads
            if not parse_source_files(upload) and upload.file_url:
                init_source_file(
                    upload,
                    path=upload.file_url,
                    filename=upload.filename,
                    kind="original",
                )

            try:
                if upload.file_url and Path(upload.file_url).exists():
                    raw = reader.read(upload.file_url)
                    processed = process_dataframe(
                        raw,
                        filename=upload.filename or ds.name,
                        description=upload.user_description,
                        use_llm=args.use_llm,
                    )
                    new_meta = processed["metadata"]
                    mapping_spec = processed["mapping_spec"]
                    clean_report = processed["clean_report"]
                    # Refresh parquet from new non-destructive cleaner
                    if not args.dry_run:
                        p = Path(upload.file_url).parent / f"{upload.id}_cleaned.parquet"
                        processed["df"].to_parquet(str(p), index=False)
                else:
                    # Fall back to existing parquet for profiling only
                    try:
                        path = ensure_cleaned_parquet(upload)
                        df = pd.read_parquet(str(path))
                    except CleanedDataMissingError:
                        skipped += 1
                        continue
                    new_meta = detector.detect(df)
                    new_meta["all_columns"] = [str(c) for c in df.columns]
                    mapping_spec = build_mapping_spec(df, new_meta, source="auto")
                    clean_report = (
                        json.loads(ds.cleaned_report_json)
                        if ds.cleaned_report_json
                        else {}
                    )

            except Exception as exc:
                errors += 1
                divergence.append(
                    {
                        "dataset_id": ds.id,
                        "name": ds.name,
                        "error": str(exc),
                    }
                )
                continue

            new_roles = {
                c["name"]: c["role"] for c in (mapping_spec.get("columns") or [])
            }
            changed = []
            for col, role in new_roles.items():
                if old.get(col) and old[col] != role:
                    changed.append({"column": col, "from": old[col], "to": role})
            for col, role in old.items():
                if col not in new_roles:
                    changed.append({"column": col, "from": role, "to": None})

            if changed:
                divergence.append(
                    {
                        "dataset_id": ds.id,
                        "name": ds.name,
                        "changes": changed,
                    }
                )

            if not args.dry_run:
                ds.mapping_spec_json = json.dumps(mapping_spec)
                ds.schema_json = json.dumps(new_meta)
                if clean_report:
                    ds.cleaned_report_json = json.dumps(clean_report)
                updated += 1

        if not args.dry_run:
            db.commit()

        report = {
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "divergence_count": len([d for d in divergence if d.get("changes")]),
            "divergence": divergence,
        }
        out_path = Path("mapping_spec_backfill_report.json")
        out_path.write_text(json.dumps(report, indent=2))
        print(json.dumps({k: report[k] for k in ("updated", "skipped", "errors", "divergence_count")}, indent=2))
        print(f"Full report written to {out_path.resolve()}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
