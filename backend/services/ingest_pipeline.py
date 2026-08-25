"""Shared ingest path for uploads, appends, and integration syncs."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models.models import Dataset, Upload, UploadStatus
from services import storage
from services.cleaned_parquet import write_cleaned_parquet
from services.column_detector import ColumnDetector
from services.column_profile import (
    build_mapping_spec,
    metadata_from_mapping_spec,
    preserve_user_mapping,
    roles_from_metadata,
    user_authored,
)
from services.column_semantics import propose_column_roles
from services.dashboard_planner import DashboardPlanner
from services.dashboard_stability import (
    parse_metadata_json,
    schema_changed,
    should_rebuild_dashboard_plan,
)
from services.data_cleaner import DataCleaner
from services.file_validation import validate_frame_size
from services.ingestion_classifier import build_ingestion_profile
from services.source_files import init_source_file

column_detector = ColumnDetector()
data_cleaner = DataCleaner()
dashboard_planner = DashboardPlanner()


def process_dataframe(
    df: pd.DataFrame,
    *,
    filename: str,
    description: str | None = None,
    drop_duplicates: bool = False,
    dayfirst: bool | None = None,
    sheet: str | None = None,
    header_row: int = 0,
    use_llm: bool = True,
    known_roles: dict[str, str] | None = None,
    known_meanings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Clean + profile + (advisory) LLM roles. Does not touch the database."""
    df, clean_report = data_cleaner.clean(
        df, drop_duplicates=drop_duplicates, dayfirst=dayfirst
    )
    metadata = column_detector.detect(df)
    metadata["all_columns"] = [str(c) for c in df.columns]

    # Merge cleaner flags into a provisional ingestion profile later
    date_formats = {}
    for col, fmt in (clean_report.get("date_formats") or {}).items():
        if isinstance(fmt, dict):
            date_formats[col] = fmt.get("format") or fmt
        else:
            date_formats[col] = fmt

    profiles = [
        {
            "name": str(c),
            "dtype": str(df[c].dtype),
            "null_rate": float(df[c].isna().mean()) if len(df) else 0.0,
            "distinct_ratio": (
                float(df[c].nunique(dropna=True) / max(df[c].notna().sum(), 1))
                if len(df)
                else 0.0
            ),
            "numeric_parse_rate": 1.0 if pd.api.types.is_numeric_dtype(df[c]) else 0.0,
            "date_parse_rate": (
                1.0 if pd.api.types.is_datetime64_any_dtype(df[c]) else 0.0
            ),
            "samples": [
                (v.isoformat() if hasattr(v, "isoformat") else v)
                for v in df[c].dropna().head(5).tolist()
            ],
        }
        for c in df.columns
    ]

    det_roles = roles_from_metadata(metadata)
    llm_result = {
        "roles": det_roles,
        "meanings": {},
        "source": "auto",
    }
    if known_roles:
        # Caller has already verified the schema is unchanged from the last
        # sync (see ingest_dataframe). Reuse the roles/meanings that were
        # validated then instead of falling back to the plain deterministic
        # guess -- that fallback is strictly weaker (no "meaning" text, and no
        # LLM correction of columns the heuristic gets wrong) and would
        # silently downgrade an already-good dataset on every unchanged
        # refresh. Restricted to columns process_dataframe still recognizes,
        # in case cleaning renamed or dropped one.
        reused_roles = {k: v for k, v in known_roles.items() if k in det_roles}
        llm_result = {
            "roles": {**det_roles, **reused_roles},
            "meanings": dict(known_meanings or {}),
            "source": "llm",
        }
        metadata = _metadata_from_roles(list(map(str, df.columns)), llm_result["roles"])
    elif use_llm:
        from services.column_profile import schema_fingerprint

        dtypes = {str(c): str(df[c].dtype) for c in df.columns}
        fp = schema_fingerprint(list(map(str, df.columns)), dtypes)
        llm_result = propose_column_roles(
            profiles,
            deterministic_roles=det_roles,
            schema_fingerprint=fp,
            filename=filename,
            user_description=description,
        )
        # Apply LLM roles back onto metadata lists
        metadata = _metadata_from_roles(list(map(str, df.columns)), llm_result["roles"])

    stats = column_detector.summary(df, metadata)
    ingestion = build_ingestion_profile(
        filename,
        description,
        metadata,
        clean_report,
        list(df.columns),
    )
    # Attach cleaner flags
    for flag in clean_report.get("flags") or []:
        codes = {f.get("code") for f in ingestion.get("flags") or []}
        if flag.get("code") not in codes:
            ingestion.setdefault("flags", []).append(flag)

    mapping_spec = build_mapping_spec(
        df,
        metadata,
        clean_report=clean_report,
        source=llm_result.get("source") or "auto",  # type: ignore[arg-type]
        sheet=sheet,
        header_row=header_row,
        date_formats={k: str(v) for k, v in date_formats.items()},
        drop_duplicates=drop_duplicates,
        dayfirst=dayfirst,
        ingestion_profile=ingestion,
        llm_meanings=llm_result.get("meanings") or {},
    )

    return {
        "df": df,
        "clean_report": clean_report,
        "metadata": metadata,
        "stats": stats,
        "ingestion": ingestion,
        "mapping_spec": mapping_spec,
    }


def _metadata_from_roles(columns: list[str], roles: dict[str, str]) -> dict[str, Any]:
    meta = {
        "date_columns": [],
        "revenue_columns": [],
        "expense_columns": [],
        "category_columns": [],
        "numeric_columns": [],
        "text_columns": [],
        "all_columns": columns,
    }
    for c in columns:
        role = roles.get(c, "text")
        if role == "timeline":
            meta["date_columns"].append(c)
        elif role == "amount_inflow":
            meta["revenue_columns"].append(c)
        elif role == "amount_outflow":
            meta["expense_columns"].append(c)
        elif role == "dimension":
            meta["category_columns"].append(c)
        elif role in ("quantity", "identifier"):
            meta["numeric_columns"].append(c)
        elif role == "ignore":
            continue
        else:
            meta["text_columns"].append(c)
    return meta


def ingest_dataframe(
    db: Session,
    *,
    df: pd.DataFrame,
    workspace_id: str,
    name: str,
    description: str | None = None,
    upload: Upload | None = None,
    dataset: Dataset | None = None,
    dashboard_plan_locked: bool = False,
    raw_source_key: str | None = None,
    raw_source_filename: str | None = None,
    raw_source_kind: str = "original",
    use_llm: bool = True,
) -> tuple[Upload, Dataset, dict]:
    """Clean, profile, and persist a dataframe as upload + dataset.

    When ``raw_source_key`` is provided it is recorded as a durable source file
    and is NOT overwritten with cleaned CSV output. Raises
    ``services.file_validation.FileValidationError`` when the incoming or
    cleaned frame exceeds the configured row/column caps -- this is the only
    caller of ``process_dataframe`` that fetches data from an external source
    with no upload-time size limit of its own, so the check has to live here.
    """
    validate_frame_size(df, filename=name)

    old_metadata = parse_metadata_json(dataset.schema_json if dataset else None)
    existing_plan = dataset.dashboard_plan_json if dataset else None
    old_mapping_spec = parse_metadata_json(dataset.mapping_spec_json if dataset else None)

    # A schema-unchanged re-sync of a locked dashboard doesn't need the LLM to
    # re-derive column roles it already derived last time -- every scheduled
    # refresh of an unchanged spreadsheet would otherwise be a paid model call,
    # forever, for data that didn't change. Comparing raw column names against
    # the last stored schema is enough: it is exactly the signature the
    # dashboard-stability check already treats as "nothing changed".
    effective_use_llm = use_llm
    known_roles: dict[str, str] | None = None
    known_meanings: dict[str, str] | None = None
    if (
        use_llm
        and dashboard_plan_locked
        and old_metadata is not None
        and not schema_changed(old_metadata, {"all_columns": [str(c) for c in df.columns]})
    ):
        effective_use_llm = False
        if old_mapping_spec:
            old_columns = old_mapping_spec.get("columns") or []
            known_roles = {
                c["name"]: c["role"] for c in old_columns if c.get("name") and c.get("role")
            }
            known_meanings = {
                c["name"]: c["meaning"] for c in old_columns if c.get("name") and c.get("meaning")
            }

    # A person who edited the mapping chose how this file should be *read*, not
    # just how it should be labelled. Cleaning with the defaults would undo that
    # on every refresh -- dates re-parsed the other way round, duplicates back.
    keep_user_mapping = user_authored(old_mapping_spec)
    policy = old_mapping_spec if keep_user_mapping else {}

    processed = process_dataframe(
        df,
        filename=name,
        description=description,
        use_llm=effective_use_llm,
        known_roles=known_roles,
        known_meanings=known_meanings,
        dayfirst=policy.get("dayfirst"),
        drop_duplicates=bool(policy.get("drop_duplicates")),
    )
    df = processed["df"]
    validate_frame_size(df, filename=name)
    clean_report = processed["clean_report"]
    metadata = processed["metadata"]
    stats = processed["stats"]
    ingestion = processed["ingestion"]
    mapping_spec = processed["mapping_spec"]
    cls_id = ingestion["classification"]["id"]

    if keep_user_mapping:
        # Roles, meanings and the chosen primary columns come back from the
        # stored spec; anything the user never touched stays as freshly
        # derived, so new columns are still profiled normally.
        mapping_spec = preserve_user_mapping(old_mapping_spec, mapping_spec)
        # schema_json, the summary stats and the dashboard plan are all derived
        # from metadata, so they have to agree with the corrected roles rather
        # than the ones the heuristic just guessed.
        metadata = metadata_from_mapping_spec(mapping_spec)
        stats = column_detector.summary(df, metadata)

    rebuild_plan = should_rebuild_dashboard_plan(
        dashboard_plan_locked=dashboard_plan_locked,
        old_metadata=old_metadata,
        new_metadata=metadata,
        existing_plan_json=existing_plan,
    )
    if rebuild_plan:
        plan = dashboard_planner.build_plan(
            df,
            metadata,
            stats,
            user_description=description,
        )
        plan_json = json.dumps(plan)
    else:
        plan_json = existing_plan or json.dumps(
            dashboard_planner.build_plan(df, metadata, stats, user_description=description)
        )

    if upload is None:
        upload = Upload(
            filename=name,
            file_type=".csv",
            file_url="",
            user_description=description,
            status=UploadStatus.processing,
            workspace_id=workspace_id,
        )
        db.add(upload)
        db.flush()

    # Durable raw source: never overwrite with cleaned output
    if raw_source_key:
        init_source_file(
            upload,
            key=raw_source_key,
            filename=raw_source_filename or name,
            kind=raw_source_kind,
        )
    else:
        # Integrations fetch fresh data each sync; this snapshot is the durable
        # artifact for that generation, stored separately from the parquet cache
        # so re-derivation never double-cleans.
        source_key = storage.upload_key(upload.id, "_source.csv")
        with storage.staged_path(source_key, suffix=".csv") as path:
            df.to_csv(str(path), index=False)
        init_source_file(
            upload,
            key=source_key,
            filename=raw_source_filename or name,
            kind="integration_sync",
        )

    upload.row_count = len(df)
    upload.column_count = len(df.columns)
    upload.status = UploadStatus.completed
    upload.filename = name
    if description is not None:
        upload.user_description = description

    write_cleaned_parquet(upload, df)

    if dataset is None:
        dataset = Dataset(
            upload_id=upload.id,
            name=name,
            schema_json=json.dumps(metadata),
            data_summary=json.dumps(stats),
            cleaned_report_json=json.dumps(clean_report),
            dashboard_plan_json=plan_json,
            dashboard_plan_locked=1 if dashboard_plan_locked else 0,
            business_classification=cls_id,
            mapping_spec_json=json.dumps(mapping_spec),
        )
        db.add(dataset)
    else:
        dataset.name = name
        dataset.schema_json = json.dumps(metadata)
        dataset.data_summary = json.dumps(stats)
        dataset.cleaned_report_json = json.dumps(clean_report)
        dataset.mapping_spec_json = json.dumps(mapping_spec)
        if rebuild_plan:
            dataset.dashboard_plan_json = plan_json
        dataset.dashboard_plan_locked = (
            1 if dashboard_plan_locked else dataset.dashboard_plan_locked
        )
        if not dataset.business_classification:
            dataset.business_classification = cls_id

    db.flush()
    return upload, dataset, ingestion
