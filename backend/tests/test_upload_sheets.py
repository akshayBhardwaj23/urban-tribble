"""Importing several tabs of one uploaded workbook as separate datasets.

An upload used to be reduced to whichever tab scored highest as a table. The
other tabs were reachable only by switching the dataset's `sheet`, which
*replaces* its rows rather than adding a second dataset -- so a workbook with a
tab per month could never be seen a month at a time.

These cover the fan-out, and the two things that had to become true for it to
work: the worker recording which tab it read, and the batch being checked
before any row is written.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from database import Base, enable_sqlite_pragmas
from models.models import Dataset, Upload, User, Workspace
from services.upload_rate_limit import reset_upload_rate_limit_for_tests
from services.upload_worker import resolve_sheet


def workbook_bytes(**tabs: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as writer:
        for name, frame in tabs.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


def _months() -> dict[str, pd.DataFrame]:
    return {
        "Jan": pd.DataFrame({"day": [1, 2, 3], "revenue": [10, 20, 30]}),
        "Feb": pd.DataFrame({"day": [1, 2, 3], "revenue": [40, 50, 60]}),
        "Mar": pd.DataFrame({"day": [1, 2, 3], "revenue": [70, 80, 90]}),
    }


class ResolveSheetTests(unittest.TestCase):
    """The worker has to name the tab it reads, or nothing downstream can tell
    which tabs of a workbook are still unimported."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _write(self, **tabs) -> str:
        path = Path(self._tmp.name) / "book.xlsx"
        path.write_bytes(workbook_bytes(**tabs))
        return str(path)

    def test_no_name_resolves_to_the_auto_pick(self):
        path = self._write(**_months())
        name, _ = resolve_sheet(path, None)
        self.assertIn(name, ("Jan", "Feb", "Mar"))

    def test_the_auto_pick_matches_what_the_reader_would_have_chosen(self):
        """list_sheets and read score and sort by the same rule, which is the
        only reason naming the tab explicitly is safe."""
        from services.file_processor import FileProcessor

        path = self._write(
            Cover=pd.DataFrame({"a": ["Quarterly report"]}),
            Data=pd.DataFrame({"day": [1, 2, 3], "revenue": [10, 20, 30]}),
        )
        name, header = resolve_sheet(path, None)
        auto = FileProcessor().read(path)
        explicit = FileProcessor().read(path, sheet_name=name, header_row=header)
        pd.testing.assert_frame_equal(auto, explicit)

    def test_a_named_tab_is_honoured(self):
        path = self._write(**_months())
        name, _ = resolve_sheet(path, "Mar")
        self.assertEqual(name, "Mar")

    def test_an_unknown_tab_is_a_readable_error(self):
        from services.file_validation import FileValidationError

        path = self._write(**_months())
        with self.assertRaises(FileValidationError) as ctx:
            resolve_sheet(path, "Apr")
        self.assertIn("Apr", str(ctx.exception))

    def test_a_csv_has_no_sheet_to_resolve(self):
        path = Path(self._tmp.name) / "data.csv"
        path.write_text("a,b\n1,2\n")
        self.assertEqual(resolve_sheet(str(path), None), (None, None))


class ImportAdditionalSheetsRouteTests(unittest.TestCase):
    """POST /api/uploads/{id}/sheets"""

    @classmethod
    def setUpClass(cls):
        from sqlalchemy.pool import StaticPool

        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        enable_sqlite_pragmas(cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from database import get_db
        from deps import require_active_workspace
        from routes import uploads as routes_uploads

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        for key, value in (
            ("UPLOAD_DIR", self._tmp.name),
            ("STORAGE_BACKEND", "local"),
            # Processing runs inline so a test sees the finished datasets
            # instead of racing a worker thread.
            ("UPLOAD_ASYNC_PROCESSING", False),
            # These cover the fan-out, not billing. Free allows two uploads for
            # a lifetime, which every multi-tab case here would trip. The quota
            # gate has its own tests below.
            ("FORCE_SUBSCRIPTION_PLAN", "internal"),
        ):
            patcher = mock.patch.object(settings, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        # process_upload opens its own SessionLocal (it normally runs on a
        # worker thread, long after the request session has closed), so it has
        # to be pointed at this engine or it would look for tables in the real
        # database.
        worker_db = mock.patch(
            "services.upload_worker.SessionLocal", self.__class__.Session
        )
        worker_db.start()
        self.addCleanup(worker_db.stop)

        # The real .env carries a live OPENAI_API_KEY; every ingest here must
        # stay off the network.
        llm = mock.patch("services.ingest_pipeline.propose_column_roles")
        self.mock_llm = llm.start()
        self.mock_llm.return_value = {"roles": {}, "meanings": {}, "source": "auto"}
        self.addCleanup(llm.stop)

        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        # The upload limiter counts in the database, so one test's uploads
        # would otherwise spend the next test's budget.
        reset_upload_rate_limit_for_tests(self.db)
        self.user = User(id="u1", email="o@x.com")
        self.db.add_all([self.user, Workspace(id="ws1", name="W", owner_id="u1")])
        self.db.commit()

        app = FastAPI()
        app.include_router(routes_uploads.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_active_workspace] = lambda: (self.user, "ws1")
        self.client = TestClient(app)

    def _wipe(self):
        db = self.Session()
        try:
            reset_upload_rate_limit_for_tests(db)
            for model in (Dataset, Upload, Workspace, User):
                db.query(model).delete()
            db.commit()
        finally:
            db.close()

    def _upload(self, **tabs) -> dict:
        resp = self.client.post(
            "/api/uploads/",
            files={
                "file": (
                    "Book.xlsx",
                    workbook_bytes(**(tabs or _months())),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data={"description": ""},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def _import(self, upload_id: str, names: list[str]):
        return self.client.post(
            f"/api/uploads/{upload_id}/sheets", json={"sheet_names": names}
        )

    def _dataset_sheets(self) -> list[str]:
        import json

        out = []
        for ds in self.db.query(Dataset).all():
            spec = json.loads(ds.mapping_spec_json or "{}")
            if spec.get("sheet"):
                out.append(spec["sheet"])
        return sorted(out)

    def test_the_first_upload_records_which_tab_it_read(self):
        """Everything else depends on this: without it the auto-picked tab
        would be offered for import and duplicated."""
        body = self._upload()
        self.assertIn(body["sheet"], ("Jan", "Feb", "Mar"))

    def test_the_remaining_tabs_are_offered(self):
        body = self._upload()
        self.assertEqual(len(body["importable_sheets"]), 2)
        self.assertNotIn(body["sheet"], body["importable_sheets"])

    def test_importing_tabs_creates_one_dataset_each(self):
        body = self._upload()
        rest = body["importable_sheets"]
        resp = self._import(body["id"], rest)
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["imported"], 2)
        self.assertEqual(self.db.query(Dataset).count(), 3)
        self.assertEqual(self._dataset_sheets(), ["Feb", "Jan", "Mar"])

    def test_each_imported_tab_reads_its_own_rows(self):
        """The point of the feature: three datasets, three different tables."""
        body = self._upload()
        self._import(body["id"], body["importable_sheets"])
        totals = set()
        for upload in self.db.query(Upload).all():
            self.assertEqual(upload.row_count, 3)
            totals.add(upload.id)
        self.assertEqual(len(totals), 3)

    def test_an_imported_tab_is_named_after_it(self):
        body = self._upload()
        self._import(body["id"], ["Feb"] if body["sheet"] != "Feb" else ["Mar"])
        names = sorted(u.filename for u in self.db.query(Upload).all())
        self.assertTrue(
            any(n.startswith("Book (") and n.endswith(").xlsx") for n in names), names
        )

    def test_importing_the_same_tab_twice_is_a_no_op(self):
        """The review step is re-rendered from sessionStorage, so a repeat
        submit is a real possibility rather than a hypothetical."""
        body = self._upload()
        target = body["importable_sheets"][0]
        self.assertEqual(self._import(body["id"], [target]).json()["imported"], 1)
        second = self._import(body["id"], [target])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["imported"], 0)
        self.assertEqual(self.db.query(Dataset).count(), 2)

    def test_the_tab_the_upload_already_read_is_never_re_imported(self):
        body = self._upload()
        resp = self._import(body["id"], [body["sheet"]])
        self.assertEqual(resp.json()["imported"], 0)
        self.assertEqual(self.db.query(Dataset).count(), 1)

    def test_an_unknown_tab_is_rejected(self):
        body = self._upload()
        resp = self._import(body["id"], ["Nope"])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Nope", resp.json()["detail"])

    def test_a_csv_has_nothing_to_import(self):
        resp = self.client.post(
            "/api/uploads/",
            files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
            data={"description": ""},
        )
        upload_id = resp.json()["id"]
        self.assertEqual(self._import(upload_id, ["Sheet1"]).status_code, 400)

    def test_deleting_one_dataset_leaves_its_siblings_readable(self):
        """Each tab gets its own copy of the bytes precisely so this holds --
        a shared storage key would be deleted out from under the others."""
        from services.source_files import delete_all_sources

        body = self._upload()
        self._import(body["id"], body["importable_sheets"])
        first = self.db.query(Upload).filter(Upload.id == body["id"]).first()
        delete_all_sources(first)

        siblings = [u for u in self.db.query(Upload).all() if u.id != body["id"]]
        self.assertEqual(len(siblings), 2)
        for upload in siblings:
            from services import storage

            self.assertTrue(storage.exists(upload.file_url), upload.filename)

    def test_a_batch_past_the_plan_quota_is_refused_before_anything_is_created(self):
        body = self._upload()
        before = self.db.query(Upload).count()
        with mock.patch.object(settings, "FORCE_SUBSCRIPTION_PLAN", "free"):
            resp = self._import(body["id"], body["importable_sheets"])
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "plan_limit")
        self.assertEqual(self.db.query(Upload).count(), before)

    def test_a_missing_upload_is_a_404(self):
        self.assertEqual(self._import("nope", ["Jan"]).status_code, 404)


if __name__ == "__main__":
    unittest.main()
