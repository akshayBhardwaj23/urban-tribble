from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from deps import require_active_workspace
from models.models import Dataset, DatasetRelation, User
from services.relation_detector import RelationDetector
from services.workspace_query import dataset_upload_pairs_for_workspace

router = APIRouter(prefix="/api/relations", tags=["relations"])

detector = RelationDetector()


@router.get("/detect")
def detect_relations(
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """Auto-detect relations across datasets in the active workspace."""
    _, workspace_id = ws
    datasets_with_meta = []

    for ds, _upload in dataset_upload_pairs_for_workspace(db, workspace_id).all():
        schema = json.loads(ds.schema_json) if ds.schema_json else {}
        all_cols = []
        for key in [
            "date_columns",
            "revenue_columns",
            "category_columns",
            "numeric_columns",
            "text_columns",
        ]:
            all_cols.extend(schema.get(key, []))

        datasets_with_meta.append(
            {
                "id": ds.id,
                "name": ds.name,
                "columns": all_cols,
                "schema": schema,
            }
        )

    relations = detector.detect_relations(datasets_with_meta)

    workspace_dataset_ids = {ds["id"] for ds in datasets_with_meta}
    if workspace_dataset_ids:
        db.query(DatasetRelation).filter(
            DatasetRelation.relation_type == "auto_detected",
            DatasetRelation.source_dataset_id.in_(workspace_dataset_ids),
        ).delete(synchronize_session=False)

    for rel in relations:
        db.add(
            DatasetRelation(
                source_dataset_id=rel["source_dataset_id"],
                target_dataset_id=rel["target_dataset_id"],
                source_column=rel["source_column"],
                target_column=rel["target_column"],
                relation_type="auto_detected",
                workspace_id=workspace_id,
            )
        )

    db.commit()

    return {"relations": relations, "total": len(relations)}


@router.get("/")
def list_relations(
    db: Session = Depends(get_db),
    ws: tuple[User, str] = Depends(require_active_workspace),
):
    """List detected and user-defined relations for the active workspace."""
    _, workspace_id = ws
    workspace_dataset_ids = [
        ds.id for ds, _ in dataset_upload_pairs_for_workspace(db, workspace_id).all()
    ]
    if not workspace_dataset_ids:
        return []

    relations = (
        db.query(DatasetRelation)
        .filter(DatasetRelation.source_dataset_id.in_(workspace_dataset_ids))
        .all()
    )

    result = []
    for rel in relations:
        source = db.query(Dataset).filter(Dataset.id == rel.source_dataset_id).first()
        target = db.query(Dataset).filter(Dataset.id == rel.target_dataset_id).first()
        result.append(
            {
                "id": rel.id,
                "source_dataset_id": rel.source_dataset_id,
                "source_dataset_name": source.name if source else "Unknown",
                "target_dataset_id": rel.target_dataset_id,
                "target_dataset_name": target.name if target else "Unknown",
                "source_column": rel.source_column,
                "target_column": rel.target_column,
                "relation_type": rel.relation_type,
                "created_at": rel.created_at.isoformat(),
            }
        )

    return result
