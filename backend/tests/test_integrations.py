"""Regression floor for the integrations subsystem.

These tests pin the behaviour that must survive turning integrations on:
the provider catalog cannot drift from the fetch dispatch, the SSRF blocklist
cannot regress, signed OAuth state cannot become forgeable, the API response
cannot start leaking stored credentials, and the sync scheduler cannot start
picking up rows it should leave alone.

Written before the hardening work so every later change has something to fail
against. Known gaps are asserted as they behave *today* and are labelled, so a
fix shows up as a deliberate test edit rather than a silent behaviour change.
"""

from __future__ import annotations

import io
import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from database import Base, enable_sqlite_pragmas
from models.models import (
    Dataset,
    DataSourceIntegration,
    IntegrationOauthSession,
    IntegrationStatus,
    Upload,
    User,
    Workspace,
)
from services import integration_connectors as conn
from services import integration_credentials as creds
from services import integration_google as gsvc
from services import integration_oauth as oauth
from services.file_validation import FileValidationError
from services.ingest_pipeline import ingest_dataframe, process_dataframe
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
    IntegrationSyncInProgressError,
)
from services.integration_credentials import decrypt_config
from services.integration_registry import PROVIDERS, get_provider, list_catalog
from services.integration_sync import (
    claim_integration_for_sync,
    compute_next_sync_at,
    count_workspace_integrations,
    find_due_integrations,
    integration_to_dict,
    sync_integration,
)

KNOWN_MODES = {"oauth", "export_url", "api_key", "service_account"}
KNOWN_FIELD_TYPES = {"text", "url", "password", "textarea", "number"}


class ProviderRegistryTests(unittest.TestCase):
    """The catalog is user-facing config; malformed entries break the UI form renderer."""

    def test_provider_ids_are_unique(self):
        ids = [p["id"] for p in PROVIDERS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_provider_is_well_formed(self):
        for p in PROVIDERS:
            with self.subTest(provider=p["id"]):
                self.assertIn(p["tier"], (1, 2, 3))
                self.assertTrue(p["name"])
                self.assertTrue(p["category"])
                self.assertTrue(p["description"])
                self.assertTrue(p["connection_modes"], "provider needs at least one mode")

    def test_every_connection_mode_is_well_formed(self):
        for p in PROVIDERS:
            seen: set[str] = set()
            for mode in p["connection_modes"]:
                with self.subTest(provider=p["id"], mode=mode["id"]):
                    self.assertIn(mode["id"], KNOWN_MODES)
                    self.assertNotIn(mode["id"], seen, "duplicate mode id on one provider")
                    seen.add(mode["id"])
                    self.assertTrue(mode["label"])
                    self.assertIsInstance(mode["fields"], list)

    def test_every_field_is_renderable(self):
        for p in PROVIDERS:
            for mode in p["connection_modes"]:
                for field in mode["fields"]:
                    with self.subTest(provider=p["id"], field=field.get("key")):
                        self.assertTrue(field.get("key"))
                        self.assertTrue(field.get("label"))
                        self.assertIn(field.get("type"), KNOWN_FIELD_TYPES)

    def test_available_modes_have_required_fields_or_are_oauth(self):
        """An available non-OAuth mode with no fields would render an empty, unusable form."""
        for p in PROVIDERS:
            for mode in p["connection_modes"]:
                if not mode.get("available", True) or mode["id"] == "oauth":
                    continue
                with self.subTest(provider=p["id"], mode=mode["id"]):
                    self.assertTrue(mode["fields"], "available credential mode needs fields")

    def test_get_provider_round_trips_and_rejects_unknown(self):
        self.assertEqual(get_provider("stripe")["name"], "Stripe")
        self.assertIsNone(get_provider("not_a_provider"))

    def test_catalog_exposes_every_provider(self):
        catalog = list_catalog()
        self.assertEqual({c["id"] for c in catalog}, {p["id"] for p in PROVIDERS})

    def test_ssrf_exposed_providers_are_not_connectable(self):
        """fetch_postgres builds an engine from a user-supplied connection
        string and fetch_salesforce GETs a user-supplied instance_url, neither
        of which passes through the SSRF blocklist that guards the export-URL
        path. Until they do, they must not be connectable. Snowflake and
        BigQuery are off for the separate reason that the warehouse tier is
        not in any launch wave."""
        for provider_id in ("postgres", "salesforce", "snowflake", "bigquery"):
            with self.subTest(provider=provider_id):
                provider = get_provider(provider_id)
                connectable = [
                    m["id"] for m in provider["connection_modes"] if m.get("available", True)
                ]
                self.assertEqual(
                    connectable, [], f"{provider_id} still has a connectable mode"
                )

    def test_disabled_modes_are_rejected_by_the_create_path(self):
        """Registry availability has to be enforced server-side, not just
        reflected in the UI -- a hand-rolled POST must be refused too."""
        from routes.integrations import _validate_connection_mode

        for provider_id, mode in (
            ("postgres", "api_key"),
            ("salesforce", "api_key"),
            ("bigquery", "service_account"),
        ):
            with self.subTest(provider=provider_id), self.assertRaises(Exception) as ctx:
                _validate_connection_mode(provider_id, mode)
            self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_wave_one_providers_remain_connectable(self):
        """Guards against over-disabling: the launch pair must stay reachable."""
        onedrive = [
            m["id"]
            for m in get_provider("excel_onedrive")["connection_modes"]
            if m.get("available", True)
        ]
        self.assertIn("oauth", onedrive)
        sheets = [
            m["id"]
            for m in get_provider("google_sheets")["connection_modes"]
            if m.get("available", True)
        ]
        self.assertTrue(sheets, "Google Sheets has no connectable mode left")


class GoogleSheetsUrlTests(unittest.TestCase):
    def test_explicit_export_url_wins(self):
        url = conn._resolve_google_sheets_url(
            {"export_url": " https://example.com/x.csv ", "spreadsheet_id": "ignored"}
        )
        self.assertEqual(url, "https://example.com/x.csv")

    def test_spreadsheet_id_builds_export_url(self):
        url = conn._resolve_google_sheets_url({"spreadsheet_id": "ABC123", "gid": "42"})
        self.assertEqual(
            url,
            "https://docs.google.com/spreadsheets/d/ABC123/export?format=csv&gid=42",
        )

    def test_gid_defaults_to_zero(self):
        url = conn._resolve_google_sheets_url({"spreadsheet_id": "ABC123"})
        self.assertTrue(url.endswith("gid=0"))

    def test_missing_everything_is_a_config_error(self):
        with self.assertRaises(IntegrationNotConfiguredError):
            conn._resolve_google_sheets_url({})


class OneDriveUrlTests(unittest.TestCase):
    def test_editor_urls_are_recognised(self):
        self.assertTrue(conn._is_excel_online_viewer_url("https://excel.cloud.microsoft/open/onedrive/?docId=1"))
        self.assertTrue(conn._is_excel_online_viewer_url("https://www.office.com/launch/excel"))
        self.assertFalse(conn._is_excel_online_viewer_url("https://1drv.ms/x/s!abc"))

    def test_share_urls_are_recognised(self):
        for url in (
            "https://1drv.ms/x/s!abc",
            "https://onedrive.live.com/view.aspx?id=1",
            "https://contoso-my.sharepoint.com/personal/x/file.xlsx",
        ):
            with self.subTest(url=url):
                self.assertTrue(conn._is_onedrive_share_url(url))
        self.assertFalse(conn._is_onedrive_share_url("https://docs.google.com/x"))

    def test_share_token_uses_microsoft_encoding(self):
        """Graph requires base64url with padding stripped and a 'u!' prefix."""
        token = conn._encode_onedrive_share_token("https://1drv.ms/x/s!AbC+d/e")
        self.assertTrue(token.startswith("u!"))
        self.assertNotIn("=", token)
        self.assertNotIn("+", token)
        self.assertNotIn("/", token[2:])

    def test_extension_guessing(self):
        self.assertEqual(conn._guess_extension("https://x/y.xlsx", ""), ".xlsx")
        self.assertEqual(conn._guess_extension("https://x/y.xls", ""), ".xls")
        self.assertEqual(conn._guess_extension("https://x/y", "text/csv"), ".csv")
        self.assertEqual(
            conn._guess_extension(
                "https://x/y",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            ".xlsx",
        )


class PayloadParsingTests(unittest.TestCase):
    def test_html_payload_is_rejected_with_actionable_message(self):
        """A login/consent page is the most common failure; it must not parse as data.

        Includes whitespace-prefixed variants: Phase 0 found that the sniffer
        used to slice before it stripped (`content[:6].lstrip()`), so a leading
        newline shifted the probe window past the `<html` marker and let a
        login page through as an empty one-column "dataset" instead of raising.
        Fixed by stripping first; kept in this table so it can't regress."""
        for body in (
            b"<!DOCTYPE html><html>...",
            b"<html><body>Sign in</body></html>",
            b"  <html><body>Sign in</body></html>",
            b"\n\n<!DOCTYPE html>\n<html>...",
        ):
            with self.subTest(body=body[:20]), self.assertRaises(IntegrationFetchError) as ctx:
                conn._dataframe_from_bytes(body, "https://x/y.csv", "text/html")
            self.assertIn("web page", str(ctx.exception).lower())

    def test_csv_payload_parses(self):
        df = conn._dataframe_from_bytes(b"a,b\n1,2\n3,4\n", "https://x/y.csv", "text/csv")
        self.assertEqual(list(df.columns), ["a", "b"])
        self.assertEqual(len(df), 2)


class MicrosoftPayloadParsingTests(unittest.IsolatedAsyncioTestCase):
    """The Microsoft Graph download path has its own inline HTML sniff,
    separate from `_dataframe_from_bytes` -- same whitespace-slicing bug
    existed here too and needed its own fix."""

    async def _download_with_body(
        self, body: bytes, *, item_name: str = "Book1.xlsx", content_type: str = "text/html"
    ):
        from services import integration_microsoft as msft

        class _FakeResponse:
            status_code = 200
            content = body
            headers = {"content-type": content_type}

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, *_a, **_kw):
                return _FakeResponse()

        with mock.patch.object(
            msft, "microsoft_ensure_access_token", new=mock.AsyncMock(return_value="tok")
        ), mock.patch.object(msft.httpx, "AsyncClient", return_value=_FakeClient()):
            return await msft.microsoft_download_item_as_dataframe(
                {"item_id": "abc", "item_name": item_name}
            )

    async def test_whitespace_prefixed_html_is_rejected(self):
        from services.integration_microsoft import IntegrationFetchError as MsftFetchError

        with self.assertRaises(MsftFetchError) as ctx:
            await self._download_with_body(b"  <html><body>Sign in</body></html>")
        self.assertIn("web page", str(ctx.exception).lower())

    async def test_csv_named_item_parses(self):
        df = await self._download_with_body(
            b"a,b\n1,2\n", item_name="Book1.csv", content_type="text/csv"
        )
        self.assertEqual(list(df.columns), ["a", "b"])


class SsrfBlocklistTests(unittest.TestCase):
    """Export URLs are fetched server-side, so the blocklist is the only thing
    standing between a pasted link and the internal network."""

    def test_loopback_and_private_ranges_are_blocked(self):
        for host in (
            "localhost",
            "127.0.0.1",
            "10.0.0.1",
            "192.168.1.1",
            "172.16.0.1",
            "0.0.0.0",
            "::1",
            "169.254.169.254",
            "metadata.google.internal",
            "foo.local",
            "svc.internal",
            "api.localhost",
            "",
        ):
            with self.subTest(host=host):
                self.assertTrue(conn._host_is_blocked(host))

    def test_public_hosts_are_allowed(self):
        for host in ("docs.google.com", "8.8.8.8", "graph.microsoft.com"):
            with self.subTest(host=host):
                self.assertFalse(conn._host_is_blocked(host))

    def test_blocked_host_url_is_rejected(self):
        with self.assertRaises(IntegrationFetchError):
            conn._assert_safe_export_url("https://169.254.169.254/latest/meta-data/")

    def test_non_http_schemes_are_rejected(self):
        for url in ("file:///etc/passwd", "gopher://x/1", "ftp://x/y.csv"):
            with self.subTest(url=url), self.assertRaises(IntegrationFetchError):
                conn._assert_safe_export_url(url)

    def test_embedded_credentials_are_rejected(self):
        with self.assertRaises(IntegrationFetchError):
            conn._assert_safe_export_url("https://user:pass@example.com/data.csv")

    def test_public_https_url_passes(self):
        conn._assert_safe_export_url("https://docs.google.com/spreadsheets/d/x/export?format=csv")


class ConnectorDispatchTests(unittest.IsolatedAsyncioTestCase):
    """The catalog and the dispatch table are edited separately and must not drift."""

    async def _dispatch_target(self, provider: str, mode: str) -> str:
        """Return the name of the fetcher fetch_provider_data routes to."""
        targets = [
            "fetch_google_sheets",
            "fetch_stripe",
            "fetch_shopify",
            "fetch_postgres",
            "fetch_excel_onedrive",
            "fetch_excel_onedrive_oauth",
            "fetch_google_sheets_oauth",
            "fetch_ga4",
            "fetch_meta_ads",
            "fetch_hubspot",
            "fetch_salesforce",
            "fetch_bigquery",
            "fetch_from_export_url",
        ]
        called: list[str] = []

        def recorder(name):
            async def _fake(_config):
                called.append(name)
                return "df"

            return _fake

        with mock.patch.multiple(
            conn, **{name: recorder(name) for name in targets}
        ):
            await conn.fetch_provider_data(provider, mode, {})
        self.assertEqual(len(called), 1, f"{provider}/{mode} hit {called}")
        return called[0]

    async def test_every_available_catalog_mode_has_a_dispatch_path(self):
        """A provider advertised as connectable must actually route somewhere."""
        for p in PROVIDERS:
            for mode in p["connection_modes"]:
                if not mode.get("available", True):
                    continue
                with self.subTest(provider=p["id"], mode=mode["id"]):
                    target = await self._dispatch_target(p["id"], mode["id"])
                    self.assertTrue(target)

    async def test_known_providers_route_to_their_own_fetcher(self):
        cases = {
            ("google_sheets", "export_url"): "fetch_google_sheets",
            ("google_sheets", "oauth"): "fetch_google_sheets_oauth",
            ("excel_onedrive", "oauth"): "fetch_excel_onedrive_oauth",
            ("excel_onedrive", "export_url"): "fetch_excel_onedrive",
            ("stripe", "api_key"): "fetch_stripe",
            ("shopify", "api_key"): "fetch_shopify",
            ("postgres", "api_key"): "fetch_postgres",
            ("ga4", "service_account"): "fetch_ga4",
            ("meta_ads", "api_key"): "fetch_meta_ads",
            ("hubspot", "api_key"): "fetch_hubspot",
            ("salesforce", "api_key"): "fetch_salesforce",
            ("bigquery", "service_account"): "fetch_bigquery",
            ("google_drive", "export_url"): "fetch_from_export_url",
            ("power_bi", "export_url"): "fetch_from_export_url",
        }
        for (provider, mode), expected in cases.items():
            with self.subTest(provider=provider, mode=mode):
                self.assertEqual(await self._dispatch_target(provider, mode), expected)

    async def test_oauth_is_wired_only_for_the_providers_that_finished_it(self):
        """Microsoft and Google are the two finished OAuth round trips. Every
        other provider advertising an `oauth` mode must fail loudly rather than
        silently falling through to some other fetcher."""
        for provider in ("google_drive", "quickbooks", "slack", "hubspot", "teams", "power_bi"):
            with self.subTest(provider=provider), self.assertRaises(IntegrationNotConfiguredError):
                await conn.fetch_provider_data(provider, "oauth", {})

    async def test_unknown_mode_is_rejected(self):
        with self.assertRaises(IntegrationNotConfiguredError):
            await conn.fetch_provider_data("stripe", "carrier_pigeon", {})


class OauthStateTests(unittest.TestCase):
    """Signed state is the CSRF boundary on the Microsoft callback."""

    def test_round_trip_preserves_payload(self):
        state = oauth.build_signed_state({"workspace_id": "ws1", "user_email": "a@b.com"})
        parsed = oauth.parse_signed_state(state)
        self.assertEqual(parsed["workspace_id"], "ws1")
        self.assertEqual(parsed["user_email"], "a@b.com")

    def test_expiry_is_stamped_by_default(self):
        parsed = oauth.parse_signed_state(oauth.build_signed_state({"a": 1}))
        self.assertIn("exp", parsed)

    def test_tampered_payload_is_rejected(self):
        state = oauth.build_signed_state({"workspace_id": "ws1"})
        body, sig = state.split(".", 1)
        forged = oauth._b64url(b'{"workspace_id":"ws-victim"}')
        with self.assertRaises(ValueError):
            oauth.parse_signed_state(f"{forged}.{sig}")

    def test_tampered_signature_is_rejected(self):
        state = oauth.build_signed_state({"workspace_id": "ws1"})
        body, _ = state.split(".", 1)
        with self.assertRaises(ValueError):
            oauth.parse_signed_state(f"{body}.{oauth._b64url(b'not-a-signature')}")

    def test_expired_state_is_rejected(self):
        past = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
        with self.assertRaises(ValueError) as ctx:
            oauth.parse_signed_state(oauth.build_signed_state({"a": 1, "exp": past}))
        self.assertIn("expired", str(ctx.exception).lower())

    def test_malformed_state_is_rejected(self):
        for bad in ("", "no-dot", "!!!.???"):
            with self.subTest(state=bad), self.assertRaises(ValueError):
                oauth.parse_signed_state(bad)

    def test_authorize_url_carries_required_params(self):
        url = oauth.build_microsoft_authorize_url("STATE123")
        for fragment in (
            "login.microsoftonline.com",
            "response_type=code",
            "state=STATE123",
            "offline_access",
            "Files.Read",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, url)


class OauthSessionStoreTests(unittest.TestCase):
    """The OAuth handoff store. This was a module-level dict, which meant the
    provider callback and the user's follow-up confirmation had to be served
    by the same worker process or the connect failed. These now go through the
    database, so the assertions deliberately use a *second, independent
    session* wherever the point is that a different worker can read it."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        enable_sqlite_pragmas(cls.engine)  # FK cascade-delete needs this explicitly now
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        # A live but invalid INTEGRATION_CREDENTIALS_KEY in the developer's
        # .env would otherwise decide whether these pass; pin the no-key
        # passthrough so this class tests the store, not the cipher.
        patcher = mock.patch.object(settings, "INTEGRATION_CREDENTIALS_KEY", "")
        patcher.start()
        self.addCleanup(patcher.stop)
        creds._cipher_cache = None
        self.addCleanup(setattr, creds, "_cipher_cache", None)

        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all(
            [User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")]
        )
        self.db.commit()

    def _wipe(self):
        db = self.Session()
        try:
            db.query(IntegrationOauthSession).delete()
            db.query(Workspace).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    def _payload(self, **kw):
        base = {
            "workspace_id": "ws1",
            "user_email": "o@x.com",
            "provider": "excel_onedrive",
            "config": {"access_token": "ms_access", "refresh_token": "ms_refresh"},
            "files": [{"id": "f1", "name": "Book1.xlsx"}],
        }
        base.update(kw)
        return base

    def test_create_then_get(self):
        sid = oauth.create_oauth_session(self.db, self._payload())
        self.assertEqual(oauth.get_oauth_session(self.db, sid)["workspace_id"], "ws1")

    def test_a_different_worker_can_read_the_session(self):
        """The whole point of this phase: the callback and the confirmation are
        separate requests and may not share a process."""
        sid = oauth.create_oauth_session(self.db, self._payload())
        other_worker = self.Session()
        try:
            loaded = oauth.get_oauth_session(other_worker, sid)
        finally:
            other_worker.close()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["config"]["refresh_token"], "ms_refresh")

    def test_payload_round_trips_completely(self):
        sid = oauth.create_oauth_session(self.db, self._payload(name="My workbook"))
        loaded = oauth.get_oauth_session(self.db, sid)
        self.assertEqual(loaded["name"], "My workbook")
        self.assertEqual(loaded["files"], [{"id": "f1", "name": "Book1.xlsx"}])

    def test_provider_tokens_are_encrypted_at_rest(self):
        """The payload carries freshly-issued access/refresh tokens. Moving this
        from memory into a table must not put them in the database as
        cleartext -- that would undo the credential encryption work."""
        with mock.patch.object(
            settings, "INTEGRATION_CREDENTIALS_KEY", creds.generate_key()
        ):
            creds._cipher_cache = None
            sid = oauth.create_oauth_session(self.db, self._payload())
            row = (
                self.db.query(IntegrationOauthSession)
                .filter(IntegrationOauthSession.id == sid)
                .first()
            )
            self.assertNotIn("ms_refresh", row.payload_json)
            self.assertNotIn("ms_access", row.payload_json)
            self.assertTrue(row.payload_json.startswith(creds.ENVELOPE_PREFIX))
            # ...and still reads back correctly through the store.
            self.assertEqual(
                oauth.get_oauth_session(self.db, sid)["config"]["refresh_token"],
                "ms_refresh",
            )
        creds._cipher_cache = None

    def test_pop_is_single_use(self):
        sid = oauth.create_oauth_session(self.db, self._payload())
        self.assertIsNotNone(oauth.pop_oauth_session(self.db, sid))
        self.assertIsNone(oauth.pop_oauth_session(self.db, sid))

    def test_pop_from_two_workers_yields_exactly_one_winner(self):
        """A double-submit must not be able to create the integration twice."""
        sid = oauth.create_oauth_session(self.db, self._payload())
        a, b = self.Session(), self.Session()
        try:
            results = [oauth.pop_oauth_session(a, sid), oauth.pop_oauth_session(b, sid)]
        finally:
            a.close()
            b.close()
        self.assertEqual(sum(1 for r in results if r is not None), 1)

    def test_pop_removes_the_row(self):
        sid = oauth.create_oauth_session(self.db, self._payload())
        oauth.pop_oauth_session(self.db, sid)
        self.assertEqual(self.db.query(IntegrationOauthSession).count(), 0)

    def test_unknown_session_is_none(self):
        self.assertIsNone(oauth.get_oauth_session(self.db, "nope"))
        self.assertIsNone(oauth.pop_oauth_session(self.db, "nope"))

    def test_expired_sessions_are_not_returned(self):
        sid = oauth.create_oauth_session(self.db, self._payload())
        row = (
            self.db.query(IntegrationOauthSession)
            .filter(IntegrationOauthSession.id == sid)
            .first()
        )
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        self.db.commit()
        self.assertIsNone(oauth.get_oauth_session(self.db, sid))

    def test_expired_sessions_are_not_popped_either(self):
        sid = oauth.create_oauth_session(self.db, self._payload())
        row = (
            self.db.query(IntegrationOauthSession)
            .filter(IntegrationOauthSession.id == sid)
            .first()
        )
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        self.db.commit()
        self.assertIsNone(oauth.pop_oauth_session(self.db, sid))
        self.assertEqual(self.db.query(IntegrationOauthSession).count(), 0)

    def test_unreadable_payload_is_discarded_rather_than_raising(self):
        """A rotated credentials key makes an in-flight session unreadable. It
        is throwaway state, so the user should be asked to reconnect, not shown
        a 500."""
        sid = oauth.create_oauth_session(self.db, self._payload())
        row = (
            self.db.query(IntegrationOauthSession)
            .filter(IntegrationOauthSession.id == sid)
            .first()
        )
        row.payload_json = creds.ENVELOPE_PREFIX + "not-a-valid-token"
        self.db.commit()
        self.assertIsNone(oauth.get_oauth_session(self.db, sid))
        self.assertEqual(self.db.query(IntegrationOauthSession).count(), 0)

    def test_creating_a_session_prunes_expired_ones(self):
        old_sid = oauth.create_oauth_session(self.db, self._payload())
        row = (
            self.db.query(IntegrationOauthSession)
            .filter(IntegrationOauthSession.id == old_sid)
            .first()
        )
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        self.db.commit()

        oauth.create_oauth_session(self.db, self._payload())
        remaining = [r.id for r in self.db.query(IntegrationOauthSession).all()]
        self.assertNotIn(old_sid, remaining)
        self.assertEqual(len(remaining), 1)

    def test_deleting_a_workspace_removes_its_pending_sessions(self):
        oauth.create_oauth_session(self.db, self._payload())
        self.db.query(Workspace).filter(Workspace.id == "ws1").delete()
        self.db.commit()
        self.assertEqual(self.db.query(IntegrationOauthSession).count(), 0)


class RefreshScheduleTests(unittest.TestCase):
    def test_interval_is_clamped_to_configured_bounds(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        too_fast = compute_next_sync_at(0, base)
        too_slow = compute_next_sync_at(10_000, base)
        self.assertEqual(too_fast, base + timedelta(hours=settings.INTEGRATION_MIN_REFRESH_HOURS))
        self.assertEqual(too_slow, base + timedelta(hours=settings.INTEGRATION_MAX_REFRESH_HOURS))

    def test_in_range_interval_is_honoured(self):
        base = datetime(2026, 1, 1, 12, 0, 0)
        self.assertEqual(compute_next_sync_at(24, base), base + timedelta(hours=24))


class IntegrationSerialisationTests(unittest.TestCase):
    def _integration(self, **kw) -> DataSourceIntegration:
        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="stripe",
            name="Stripe revenue",
            connection_mode="api_key",
            config_json='{"secret_key": "sk_live_SUPERSECRET"}',
            refresh_interval_hours=24,
            status=IntegrationStatus.active,
            **kw,
        )
        row.id = "int1"
        row.created_at = datetime(2026, 1, 1, 12, 0, 0)
        return row

    def test_response_never_contains_stored_credentials(self):
        """The connect form posts secrets; no read path may echo them back."""
        payload = integration_to_dict(self._integration(), provider_name="Stripe")
        blob = repr(payload)
        self.assertNotIn("SUPERSECRET", blob)
        self.assertNotIn("config_json", payload)
        self.assertNotIn("config", payload)
        self.assertTrue(payload["has_credentials"])

    def test_has_credentials_is_false_without_config(self):
        row = self._integration()
        row.config_json = None
        self.assertFalse(integration_to_dict(row)["has_credentials"])

    def test_status_is_serialised_as_its_value(self):
        payload = integration_to_dict(self._integration())
        self.assertEqual(payload["status"], "active")

    def test_provider_name_falls_back_to_provider_id(self):
        self.assertEqual(integration_to_dict(self._integration())["provider_name"], "stripe")


class DueIntegrationTests(unittest.TestCase):
    """Which rows the scheduler picks up. Getting this wrong means either a
    stalled connection or a runaway refresh loop."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        enable_sqlite_pragmas(cls.engine)  # FK cascade-delete needs this explicitly now
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        # These exercise the scheduling machinery itself, so they opt into
        # unattended syncing; it is off by default (see ManualOnlySyncTests).
        auto = mock.patch.object(settings, "INTEGRATION_AUTO_SYNC_ENABLED", True)
        auto.start()
        self.addCleanup(auto.stop)

        self.db = self.Session()
        self.addCleanup(self.db.close)
        user = User(id="u1", email="owner@example.com")
        ws = Workspace(id="ws1", name="Test workspace", owner_id="u1")
        self.db.add_all([user, ws])
        self.db.commit()
        self.addCleanup(self._wipe_all)

    def _wipe_integrations(self):
        self.db.query(DataSourceIntegration).delete()
        self.db.commit()

    def _wipe_all(self):
        db = self.Session()
        try:
            db.query(DataSourceIntegration).delete()
            db.query(Workspace).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    def _add(
        self,
        *,
        status: IntegrationStatus,
        next_sync_at,
        name="s",
        syncing_started_at=None,
    ) -> DataSourceIntegration:
        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="google_sheets",
            name=name,
            connection_mode="export_url",
            refresh_interval_hours=24,
            status=status,
            next_sync_at=next_sync_at,
            syncing_started_at=syncing_started_at,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def test_overdue_rows_are_picked_up(self):
        past = datetime.utcnow() - timedelta(hours=1)
        for status in (IntegrationStatus.active, IntegrationStatus.pending, IntegrationStatus.error):
            with self.subTest(status=status):
                self._wipe_integrations()
                self._add(status=status, next_sync_at=past)
                self.assertEqual(len(find_due_integrations(self.db)), 1)

    def test_future_rows_are_left_alone(self):
        self._add(
            status=IntegrationStatus.active,
            next_sync_at=datetime.utcnow() + timedelta(hours=1),
        )
        self.assertEqual(find_due_integrations(self.db), [])

    def test_rows_without_a_schedule_are_left_alone(self):
        self._add(status=IntegrationStatus.active, next_sync_at=None)
        self.assertEqual(find_due_integrations(self.db), [])

    def test_disconnected_rows_are_never_synced(self):
        self._add(
            status=IntegrationStatus.disconnected,
            next_sync_at=datetime.utcnow() - timedelta(hours=1),
        )
        self.assertEqual(find_due_integrations(self.db), [])

    def test_stale_syncing_rows_are_reclaimed(self):
        """Phase 2 fix for the gap the previous test named: a crash mid-sync
        must not brick the row forever. A `syncing` row whose heartbeat is
        older than INTEGRATION_STALE_SYNC_MINUTES is due again."""
        stale = datetime.utcnow() - timedelta(minutes=settings.INTEGRATION_STALE_SYNC_MINUTES + 5)
        self._add(
            status=IntegrationStatus.syncing,
            next_sync_at=datetime.utcnow() - timedelta(days=7),
            syncing_started_at=stale,
        )
        self.assertEqual(len(find_due_integrations(self.db)), 1)

    def test_syncing_rows_with_no_heartbeat_are_reclaimed(self):
        """A row already stuck in `syncing` from before this column existed has
        syncing_started_at=NULL. It must not be stuck forever just because it
        predates the fix -- treated the same as a stale heartbeat."""
        self._add(
            status=IntegrationStatus.syncing,
            next_sync_at=datetime.utcnow() - timedelta(days=7),
            syncing_started_at=None,
        )
        self.assertEqual(len(find_due_integrations(self.db)), 1)

    def test_freshly_syncing_rows_are_not_reclaimed(self):
        """A sync that is genuinely in progress right now must not be treated
        as due again just because its next_sync_at is in the past."""
        fresh = datetime.utcnow() - timedelta(minutes=1)
        self._add(
            status=IntegrationStatus.syncing,
            next_sync_at=datetime.utcnow() - timedelta(hours=1),
            syncing_started_at=fresh,
        )
        self.assertEqual(find_due_integrations(self.db), [])

    def test_results_are_oldest_first_and_capped(self):
        now = datetime.utcnow()
        for i in range(5):
            self._add(
                status=IntegrationStatus.active,
                next_sync_at=now - timedelta(hours=10 - i),
                name=f"s{i}",
            )
        due = find_due_integrations(self.db, limit=3)
        self.assertEqual([r.name for r in due], ["s0", "s1", "s2"])


class CredentialEncryptionTests(unittest.TestCase):
    """`config_json` holds live third-party secrets. These pin the envelope
    format, the legacy-cleartext read path, and the failure modes that must
    surface as a readable error rather than silently losing credentials."""

    SECRET = {"secret_key": "sk_live_SUPERSECRET", "days_back": 90}

    def setUp(self):
        creds._cipher_cache = None
        self.addCleanup(setattr, creds, "_cipher_cache", None)

    def _with_keys(self, value: str):
        patcher = mock.patch.object(settings, "INTEGRATION_CREDENTIALS_KEY", value)
        patcher.start()
        self.addCleanup(patcher.stop)
        creds._cipher_cache = None

    def test_generated_key_is_usable(self):
        self._with_keys(creds.generate_key())
        self.assertTrue(creds.encryption_enabled())
        self.assertIsNone(creds.validate_configured_keys())

    def test_round_trip_under_a_key(self):
        self._with_keys(creds.generate_key())
        stored = creds.encrypt_config(self.SECRET)
        self.assertEqual(creds.decrypt_config(stored), self.SECRET)

    def test_stored_value_does_not_contain_the_secret(self):
        self._with_keys(creds.generate_key())
        stored = creds.encrypt_config(self.SECRET)
        self.assertTrue(stored.startswith(creds.ENVELOPE_PREFIX))
        self.assertNotIn("SUPERSECRET", stored)
        self.assertNotIn("secret_key", stored)

    def test_ciphertext_differs_across_writes(self):
        """Fernet stamps a random IV, so identical credentials must not produce
        identical rows — otherwise the column leaks which tenants share a key."""
        self._with_keys(creds.generate_key())
        self.assertNotEqual(
            creds.encrypt_config(self.SECRET), creds.encrypt_config(self.SECRET)
        )

    def test_tampered_ciphertext_is_rejected(self):
        """Fernet is authenticated; a flipped byte must fail, not decrypt to junk."""
        self._with_keys(creds.generate_key())
        stored = creds.encrypt_config(self.SECRET)
        body = stored[len(creds.ENVELOPE_PREFIX) :]
        tampered = creds.ENVELOPE_PREFIX + body[:-4] + ("AAAA" if body[-4:] != "AAAA" else "BBBB")
        with self.assertRaises(creds.IntegrationCredentialsError):
            creds.decrypt_config(tampered)

    def test_wrong_key_is_rejected_with_an_actionable_message(self):
        self._with_keys(creds.generate_key())
        stored = creds.encrypt_config(self.SECRET)
        self._with_keys(creds.generate_key())
        with self.assertRaises(creds.IntegrationCredentialsError) as ctx:
            creds.decrypt_config(stored)
        self.assertIn("rotated", str(ctx.exception).lower())

    def test_rotation_keeps_old_ciphertext_readable(self):
        old_key = creds.generate_key()
        self._with_keys(old_key)
        stored = creds.encrypt_config(self.SECRET)

        new_key = creds.generate_key()
        self._with_keys(f"{new_key},{old_key}")
        self.assertEqual(creds.decrypt_config(stored), self.SECRET)

        # New writes seal under the new primary key only.
        resealed = creds.encrypt_config(self.SECRET)
        self._with_keys(new_key)
        self.assertEqual(creds.decrypt_config(resealed), self.SECRET)

    def test_legacy_cleartext_rows_still_read(self):
        """Rows written before this change must keep working after the key lands."""
        self._with_keys(creds.generate_key())
        self.assertEqual(creds.decrypt_config('{"secret_key": "sk_legacy"}'),
                         {"secret_key": "sk_legacy"})

    def test_encrypted_row_without_a_key_fails_loudly(self):
        """Losing the key must not look like 'this integration has no credentials'."""
        self._with_keys(creds.generate_key())
        stored = creds.encrypt_config(self.SECRET)
        self._with_keys("")
        with self.assertRaises(creds.IntegrationCredentialsError) as ctx:
            creds.decrypt_config(stored)
        self.assertIn("INTEGRATION_CREDENTIALS_KEY", str(ctx.exception))

    def test_passthrough_when_no_key_is_configured(self):
        """Unchanged development behaviour: cleartext in, cleartext out."""
        self._with_keys("")
        stored = creds.encrypt_config(self.SECRET)
        self.assertFalse(creds.is_encrypted(stored))
        self.assertEqual(creds.decrypt_config(stored), self.SECRET)

    def test_empty_and_unreadable_values_read_as_no_credentials(self):
        self._with_keys("")
        for raw in (None, "", "not json at all", "[1,2,3]"):
            with self.subTest(raw=raw):
                self.assertEqual(creds.decrypt_config(raw), {})

    def test_malformed_key_is_reported_not_raised_at_import(self):
        self._with_keys("this-is-not-a-fernet-key")
        message = creds.validate_configured_keys()
        self.assertIsNotNone(message)
        self.assertIn("INTEGRATION_CREDENTIALS_KEY", message)

    def test_credentials_error_is_handled_by_existing_sync_error_paths(self):
        """Subclassing IntegrationNotConfiguredError is what makes an unreadable
        row a 422 that parks the integration in `error`, instead of a 500."""
        self.assertTrue(
            issubclass(creds.IntegrationCredentialsError, IntegrationNotConfiguredError)
        )
        self.assertTrue(issubclass(creds.IntegrationCredentialsError, IntegrationFetchError))


class ProductionGuardTests(unittest.TestCase):
    """The guard is the only thing stopping a production deploy from writing
    customer secrets to the database in cleartext."""

    def _errors_for(self, **overrides) -> list[str]:
        from config import Settings, collect_runtime_setting_errors

        base = {
            "APP_ENV": "production",
            "INTEGRATION_CREDENTIALS_KEY": creds.generate_key(),
        }
        base.update(overrides)
        return collect_runtime_setting_errors(Settings(**base))

    def test_missing_credentials_key_blocks_production_boot(self):
        errors = self._errors_for(INTEGRATION_CREDENTIALS_KEY="")
        self.assertTrue(
            any("INTEGRATION_CREDENTIALS_KEY" in e for e in errors),
            "production boot must be refused without a credentials key",
        )

    def test_malformed_credentials_key_blocks_production_boot(self):
        errors = self._errors_for(INTEGRATION_CREDENTIALS_KEY="nope")
        self.assertTrue(any("INTEGRATION_CREDENTIALS_KEY" in e for e in errors))

    def test_valid_key_raises_no_credential_complaint(self):
        errors = self._errors_for()
        self.assertFalse([e for e in errors if "INTEGRATION_CREDENTIALS_KEY" in e])

    def test_development_is_unaffected(self):
        from config import Settings, collect_runtime_setting_errors

        self.assertEqual(
            collect_runtime_setting_errors(
                Settings(APP_ENV="development", INTEGRATION_CREDENTIALS_KEY="")
            ),
            [],
        )


class StoredIntegrationRoundTripTests(unittest.TestCase):
    """End to end through the model column, the way the routes use it."""

    def setUp(self):
        creds._cipher_cache = None
        patcher = mock.patch.object(
            settings, "INTEGRATION_CREDENTIALS_KEY", creds.generate_key()
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, creds, "_cipher_cache", None)

    def test_column_holds_ciphertext_but_reads_back_as_credentials(self):
        from services.integration_sync import _load_config

        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="shopify",
            name="Shopify orders",
            connection_mode="api_key",
            config_json=creds.encrypt_config({"access_token": "shpat_SECRET"}),
            refresh_interval_hours=24,
            status=IntegrationStatus.active,
        )
        self.assertNotIn("shpat_SECRET", row.config_json)
        self.assertEqual(_load_config(row), {"access_token": "shpat_SECRET"})

    def test_api_payload_still_hides_credentials_when_encrypted(self):
        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="shopify",
            name="Shopify orders",
            connection_mode="api_key",
            config_json=creds.encrypt_config({"access_token": "shpat_SECRET"}),
            refresh_interval_hours=24,
            status=IntegrationStatus.active,
        )
        row.id = "int1"
        row.created_at = datetime(2026, 1, 1, 12, 0, 0)
        payload = integration_to_dict(row, provider_name="Shopify")
        self.assertNotIn("shpat_SECRET", repr(payload))
        self.assertNotIn(creds.ENVELOPE_PREFIX, repr(payload))
        self.assertTrue(payload["has_credentials"])


class ProcessDataframeKnownRolesTests(unittest.TestCase):
    """`known_roles`/`known_meanings` let a caller that has already verified
    the schema is unchanged reuse validated labels instead of paying for a
    fresh LLM call or silently falling back to the weaker deterministic guess.
    """

    def _df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "order_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "revenue": [100.0, 200.0, 150.0],
            }
        )

    def test_known_roles_skip_the_llm_call(self):
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            result = process_dataframe(
                self._df(),
                filename="sheet.csv",
                known_roles={"order_date": "timeline", "revenue": "amount_inflow"},
                known_meanings={"revenue": "Gross order value"},
            )
        m.assert_not_called()
        columns_by_name = {c["name"]: c for c in result["mapping_spec"]["columns"]}
        self.assertEqual(columns_by_name["order_date"]["role"], "timeline")
        self.assertEqual(columns_by_name["revenue"]["role"], "amount_inflow")
        self.assertEqual(columns_by_name["revenue"]["meaning"], "Gross order value")
        self.assertEqual(result["mapping_spec"]["source"], "llm")

    def test_no_known_roles_calls_the_llm_when_enabled(self):
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            m.return_value = {"roles": {}, "meanings": {}, "source": "auto"}
            process_dataframe(self._df(), filename="sheet.csv", use_llm=True)
        m.assert_called_once()

    def test_no_known_roles_and_use_llm_false_skips_without_reuse(self):
        """Unchanged upload-path behaviour: no known roles means no reuse
        mechanism kicks in, so use_llm still governs it exactly as before."""
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            result = process_dataframe(self._df(), filename="sheet.csv", use_llm=False)
        m.assert_not_called()
        self.assertEqual(result["mapping_spec"]["source"], "auto")

    def test_known_role_for_a_column_that_no_longer_exists_is_dropped_safely(self):
        """Defensive: a stale known_roles entry must not raise or leak in."""
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            result = process_dataframe(
                self._df(),
                filename="sheet.csv",
                known_roles={"revenue": "amount_inflow", "ghost_column": "dimension"},
            )
        m.assert_not_called()
        names = {c["name"] for c in result["mapping_spec"]["columns"]}
        self.assertNotIn("ghost_column", names)


class IngestDataframeSafetyTests(unittest.TestCase):
    """`ingest_dataframe` is shared with uploads, so these pin the two things
    Phase 2 adds to it: a frame-size ceiling, and the schema-unchanged LLM skip
    -- without changing upload behaviour, which never sets dashboard_plan_locked
    with a pre-existing dataset in the same way an integration sync does."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        enable_sqlite_pragmas(cls.engine)  # FK cascade-delete needs this explicitly now
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        import tempfile

        # These exercise the scheduling machinery itself, so they opt into
        # unattended syncing; it is off by default (see ManualOnlySyncTests).
        auto = mock.patch.object(settings, "INTEGRATION_AUTO_SYNC_ENABLED", True)
        auto.start()
        self.addCleanup(auto.stop)

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = mock.patch.object(settings, "UPLOAD_DIR", self._tmpdir.name)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all([User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")])
        self.db.commit()

    def _wipe(self):
        db = self.Session()
        try:
            db.query(Dataset).delete()
            db.query(Upload).delete()
            db.query(Workspace).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    def _df(self, revenue_col: str = "revenue") -> pd.DataFrame:
        return pd.DataFrame(
            {
                "order_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                revenue_col: [100.0, 200.0, 150.0],
            }
        )

    def test_oversized_frame_is_rejected_before_processing(self):
        with mock.patch.object(settings, "MAX_ROWS_PER_FILE", 2), mock.patch(
            "services.ingest_pipeline.propose_column_roles"
        ) as m:
            with self.assertRaises(FileValidationError):
                ingest_dataframe(
                    self.db, df=self._df(), workspace_id="ws1", name="Big", use_llm=False
                )
        m.assert_not_called()

    def test_first_sync_always_calls_the_llm_even_when_locked(self):
        """No prior dataset means there is nothing safe to reuse yet."""
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            m.return_value = {
                "roles": {"order_date": "timeline", "revenue": "amount_inflow"},
                "meanings": {"revenue": "Order value"},
                "source": "llm",
            }
            ingest_dataframe(
                self.db,
                df=self._df(),
                workspace_id="ws1",
                name="Stripe revenue",
                dashboard_plan_locked=True,
                use_llm=True,
            )
        m.assert_called_once()

    def test_unchanged_schema_on_a_locked_resync_skips_the_llm_and_reuses_labels(self):
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            m.return_value = {
                "roles": {"order_date": "timeline", "revenue": "amount_inflow"},
                "meanings": {"revenue": "Order value"},
                "source": "llm",
            }
            upload, dataset, _ = ingest_dataframe(
                self.db,
                df=self._df(),
                workspace_id="ws1",
                name="Stripe revenue",
                dashboard_plan_locked=True,
                use_llm=True,
            )
        m.assert_called_once()

        with mock.patch("services.ingest_pipeline.propose_column_roles") as m2:
            ingest_dataframe(
                self.db,
                df=self._df(),
                workspace_id="ws1",
                name="Stripe revenue",
                upload=upload,
                dataset=dataset,
                dashboard_plan_locked=True,
                use_llm=True,
            )
        m2.assert_not_called()
        spec = json.loads(dataset.mapping_spec_json)
        by_name = {c["name"]: c for c in spec["columns"]}
        self.assertEqual(by_name["revenue"]["role"], "amount_inflow")
        self.assertEqual(by_name["revenue"]["meaning"], "Order value")

    def test_changed_schema_on_a_locked_resync_still_calls_the_llm(self):
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            m.return_value = {"roles": {}, "meanings": {}, "source": "llm"}
            upload, dataset, _ = ingest_dataframe(
                self.db,
                df=self._df(),
                workspace_id="ws1",
                name="Stripe revenue",
                dashboard_plan_locked=True,
                use_llm=True,
            )

        with mock.patch("services.ingest_pipeline.propose_column_roles") as m2:
            m2.return_value = {"roles": {}, "meanings": {}, "source": "llm"}
            ingest_dataframe(
                self.db,
                df=self._df(revenue_col="net_revenue"),  # column renamed -> schema changed
                workspace_id="ws1",
                name="Stripe revenue",
                upload=upload,
                dataset=dataset,
                dashboard_plan_locked=True,
                use_llm=True,
            )
        m2.assert_called_once()

    def test_unlocked_resync_still_calls_the_llm_even_with_unchanged_schema(self):
        """The skip is specifically for locked dashboards; an unlocked one is
        expected to re-derive on every sync, so it must not be short-circuited."""
        with mock.patch("services.ingest_pipeline.propose_column_roles") as m:
            m.return_value = {"roles": {}, "meanings": {}, "source": "llm"}
            upload, dataset, _ = ingest_dataframe(
                self.db,
                df=self._df(),
                workspace_id="ws1",
                name="Stripe revenue",
                dashboard_plan_locked=False,
                use_llm=True,
            )

        with mock.patch("services.ingest_pipeline.propose_column_roles") as m2:
            m2.return_value = {"roles": {}, "meanings": {}, "source": "llm"}
            ingest_dataframe(
                self.db,
                df=self._df(),
                workspace_id="ws1",
                name="Stripe revenue",
                upload=upload,
                dataset=dataset,
                dashboard_plan_locked=False,
                use_llm=True,
            )
        m2.assert_called_once()


class ClaimIntegrationForSyncTests(unittest.TestCase):
    """Deterministic, single-threaded coverage of the compare-and-swap logic
    itself. `ClaimConcurrencyTests` below additionally proves the property
    under real concurrent Postgres transactions -- this class pins the plain
    decision table so a regression fails fast, without needing a database
    server to run."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        enable_sqlite_pragmas(cls.engine)  # FK cascade-delete needs this explicitly now
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all([User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")])
        self.db.commit()

    def _wipe(self):
        db = self.Session()
        try:
            db.query(DataSourceIntegration).delete()
            db.query(Workspace).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    def _add(self, **kw) -> DataSourceIntegration:
        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="stripe",
            name="s",
            connection_mode="api_key",
            refresh_interval_hours=24,
            **kw,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def test_pending_row_is_claimable(self):
        row = self._add(status=IntegrationStatus.pending)
        self.assertTrue(claim_integration_for_sync(self.db, row.id))
        self.db.refresh(row)
        self.assertEqual(row.status, IntegrationStatus.syncing)
        self.assertIsNotNone(row.syncing_started_at)

    def test_error_and_active_rows_are_claimable(self):
        for status in (IntegrationStatus.error, IntegrationStatus.active):
            with self.subTest(status=status):
                self._wipe()
                self.db.add_all(
                    [User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")]
                )
                self.db.commit()
                row = self._add(status=status, last_sync_error="boom")
                self.assertTrue(claim_integration_for_sync(self.db, row.id))
                self.db.refresh(row)
                self.assertIsNone(row.last_sync_error)

    def test_freshly_syncing_row_cannot_be_claimed(self):
        row = self._add(
            status=IntegrationStatus.syncing,
            syncing_started_at=datetime.utcnow() - timedelta(minutes=1),
        )
        self.assertFalse(claim_integration_for_sync(self.db, row.id))
        self.db.refresh(row)
        self.assertEqual(row.status, IntegrationStatus.syncing)

    def test_stale_syncing_row_is_claimable(self):
        row = self._add(
            status=IntegrationStatus.syncing,
            syncing_started_at=datetime.utcnow()
            - timedelta(minutes=settings.INTEGRATION_STALE_SYNC_MINUTES + 1),
        )
        self.assertTrue(claim_integration_for_sync(self.db, row.id))

    def test_syncing_row_with_no_heartbeat_is_claimable(self):
        """Predates the heartbeat column; must not be permanently stuck."""
        row = self._add(status=IntegrationStatus.syncing, syncing_started_at=None)
        self.assertTrue(claim_integration_for_sync(self.db, row.id))

    def test_claiming_twice_in_a_row_the_second_call_loses(self):
        row = self._add(status=IntegrationStatus.pending)
        self.assertTrue(claim_integration_for_sync(self.db, row.id))
        self.assertFalse(claim_integration_for_sync(self.db, row.id))

    def test_nonexistent_row_is_not_claimable(self):
        self.assertFalse(claim_integration_for_sync(self.db, "does-not-exist"))

    def test_count_workspace_integrations(self):
        self.assertEqual(count_workspace_integrations(self.db, "ws1"), 0)
        self._add(status=IntegrationStatus.active)
        self._add(status=IntegrationStatus.active)
        self.assertEqual(count_workspace_integrations(self.db, "ws1"), 2)
        self.assertEqual(count_workspace_integrations(self.db, "some-other-ws"), 0)


class ClaimConcurrencyTests(unittest.TestCase):
    """Real concurrent-transaction proof for the compare-and-swap claim.

    SQLite serializes writers at the file/connection level regardless of
    whether the WHERE clause is correct, so it cannot expose a broken
    compare-and-swap the way independent Postgres connections with row-level
    locking can. Skipped unless a real Postgres is reachable -- this is the
    one test in the suite that needs a database server, because it is
    checking a property (exactly-one-winner under genuine interleaving) that
    a single-process fake cannot demonstrate.

    **CI runs this** against the throwaway Postgres service already defined in
    .github/workflows/ci.yml, on the schema the migration step just built. It
    is skipped locally only so the everyday suite needs no database server;
    point INTEGRATION_TEST_POSTGRES_URL at a throwaway database to run it by
    hand.

    DESTRUCTIVE: truncates users, workspaces and integrations before seeding
    its race row. Never point INTEGRATION_TEST_POSTGRES_URL at a database with
    real data in it.
    """

    @classmethod
    def setUpClass(cls):
        import os

        url = os.environ.get("INTEGRATION_TEST_POSTGRES_URL")
        if not url:
            raise unittest.SkipTest(
                "Set INTEGRATION_TEST_POSTGRES_URL to a throwaway Postgres database "
                "to run the real-concurrency claim test."
            )
        from sqlalchemy import create_engine as _create_engine

        cls.engine = _create_engine(url)
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def test_concurrent_claims_have_exactly_one_winner(self):
        import threading

        db = self.Session()
        db.query(DataSourceIntegration).delete()
        db.query(Workspace).delete()
        db.query(User).delete()
        db.add_all([User(id="u1", email="race@x.com"), Workspace(id="ws1", name="W", owner_id="u1")])
        db.commit()
        row = DataSourceIntegration(
            id="race1",
            workspace_id="ws1",
            provider="stripe",
            name="Race target",
            connection_mode="api_key",
            refresh_interval_hours=24,
            status=IntegrationStatus.pending,
        )
        db.add(row)
        db.commit()
        db.close()

        n = 20
        results: list[bool] = []
        lock = threading.Lock()
        barrier = threading.Barrier(n)

        def worker():
            barrier.wait()
            session = self.Session()
            try:
                won = claim_integration_for_sync(session, "race1")
            finally:
                session.close()
            with lock:
                results.append(won)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sum(results), 1)


class WorkspaceIntegrationCapTests(unittest.TestCase):
    """Bounds worst-case scheduled fetch + LLM volume per workspace,
    independent of any plan tier."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        enable_sqlite_pragmas(cls.engine)  # FK cascade-delete needs this explicitly now
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all([
            User(id="u1", email="o@x.com"),
            Workspace(id="ws1", name="W1", owner_id="u1"),
            Workspace(id="ws2", name="W2", owner_id="u1"),
        ])
        self.db.commit()

    def _wipe(self):
        db = self.Session()
        try:
            db.query(DataSourceIntegration).delete()
            db.query(Workspace).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    def _add(self, workspace_id: str) -> None:
        self.db.add(
            DataSourceIntegration(
                workspace_id=workspace_id,
                provider="google_sheets",
                name="s",
                connection_mode="export_url",
                refresh_interval_hours=24,
                status=IntegrationStatus.active,
            )
        )
        self.db.commit()

    def test_count_is_scoped_to_one_workspace(self):
        self._add("ws1")
        self._add("ws1")
        self._add("ws2")
        self.assertEqual(count_workspace_integrations(self.db, "ws1"), 2)
        self.assertEqual(count_workspace_integrations(self.db, "ws2"), 1)

    def test_count_is_zero_for_a_workspace_with_none(self):
        self.assertEqual(count_workspace_integrations(self.db, "ws1"), 0)

    def test_route_helper_blocks_at_the_configured_cap(self):
        from routes.integrations import _require_workspace_capacity

        with mock.patch.object(settings, "INTEGRATION_MAX_PER_WORKSPACE", 2):
            self._add("ws1")
            _require_workspace_capacity(self.db, "ws1")  # 1 of 2: fine
            self._add("ws1")
            with self.assertRaises(Exception) as ctx:
                _require_workspace_capacity(self.db, "ws1")  # 2 of 2: blocked
            self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_route_helper_is_a_noop_when_cap_is_zero(self):
        """0 is treated as unlimited, matching the `if cap and ...` guard."""
        from routes.integrations import _require_workspace_capacity

        with mock.patch.object(settings, "INTEGRATION_MAX_PER_WORKSPACE", 0):
            for _ in range(5):
                self._add("ws1")
            _require_workspace_capacity(self.db, "ws1")  # must not raise


class SyncIntegrationEndToEndTests(unittest.IsolatedAsyncioTestCase):
    """The full sync_integration flow against a real database, with the
    network call mocked. This is what Phase 2 actually promises: the row
    never ends up stuck in `syncing`, no matter which stage fails."""

    @classmethod
    def setUpClass(cls):
        # sync_integration offloads ingest_dataframe onto a worker thread
        # (see services.integration_sync's use of loop.run_in_executor), so
        # this engine is touched from a different OS thread than the one that
        # created it -- exactly the case database.py's own check_same_thread
        # override exists for. Without it, a real bare `sqlite://` connection
        # raises "SQLite objects created in a thread can only be used in that
        # same thread" the moment the executor thread uses it.
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        enable_sqlite_pragmas(cls.engine)  # FK cascade-delete needs this explicitly now
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        import tempfile

        # These exercise the scheduling machinery itself, so they opt into
        # unattended syncing; it is off by default (see ManualOnlySyncTests).
        auto = mock.patch.object(settings, "INTEGRATION_AUTO_SYNC_ENABLED", True)
        auto.start()
        self.addCleanup(auto.stop)

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = mock.patch.object(settings, "UPLOAD_DIR", self._tmpdir.name)
        patcher.start()
        self.addCleanup(patcher.stop)

        # This backend's real .env carries a placeholder INTEGRATION_CREDENTIALS_KEY
        # that is not a valid Fernet key (pydantic-settings loads it regardless of
        # test env vars). Force the passthrough/no-key mode so encrypt_config never
        # depends on ambient dev-machine state -- what's under test here is sync
        # behaviour, not encryption, which already has its own dedicated suite.
        creds_patcher = mock.patch.object(settings, "INTEGRATION_CREDENTIALS_KEY", "")
        creds_patcher.start()
        self.addCleanup(creds_patcher.stop)
        creds._cipher_cache = None
        self.addCleanup(setattr, creds, "_cipher_cache", None)

        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all([User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")])
        self.db.commit()

        # process_dataframe defaults to use_llm=True, and this backend's real
        # .env carries a live OPENAI_API_KEY -- every test here must mock the
        # LLM call so the suite never places a real, billed request.
        llm_patcher = mock.patch("services.ingest_pipeline.propose_column_roles")
        self.mock_llm = llm_patcher.start()
        self.mock_llm.return_value = {"roles": {}, "meanings": {}, "source": "auto"}
        self.addCleanup(llm_patcher.stop)

    def _wipe(self):
        db = self.Session()
        try:
            db.query(Dataset).delete()
            db.query(Upload).delete()
            db.query(DataSourceIntegration).delete()
            db.query(Workspace).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    def _df(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "order_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "revenue": [100.0, 200.0, 150.0],
            }
        )

    def _integration(self, **kw) -> DataSourceIntegration:
        defaults = {
            "workspace_id": "ws1",
            "provider": "stripe",
            "name": "Stripe revenue",
            "connection_mode": "api_key",
            "config_json": creds.encrypt_config({"secret_key": "sk_test_x"}),
            "refresh_interval_hours": 24,
            "status": IntegrationStatus.pending,
            "next_sync_at": datetime.utcnow(),
            "auto_analyze": 0,
        }
        defaults.update(kw)
        row = DataSourceIntegration(**defaults)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    async def test_first_sync_succeeds_and_creates_a_dataset(self):
        integration = self._integration()
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ):
            result = await sync_integration(self.db, integration, trigger="manual")

        self.assertEqual(result["row_count"], 3)
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.active)
        self.assertIsNotNone(integration.dataset_id)
        self.assertIsNotNone(integration.last_sync_at)
        self.assertIsNotNone(integration.next_sync_at)
        self.assertIsNone(integration.syncing_started_at)
        self.assertIsNone(integration.last_sync_error)

    async def test_resync_reuses_the_existing_dataset(self):
        integration = self._integration()
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ):
            first = await sync_integration(self.db, integration, trigger="manual")
            second = await sync_integration(self.db, integration, trigger="scheduled")
        self.assertEqual(first["dataset_id"], second["dataset_id"])

    async def test_fetch_failure_leaves_the_row_in_error_not_syncing(self):
        integration = self._integration()
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(side_effect=IntegrationFetchError("Invalid API key")),
        ):
            with self.assertRaises(IntegrationFetchError):
                await sync_integration(self.db, integration, trigger="manual")
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.error)
        self.assertEqual(integration.last_sync_error, "Invalid API key")
        self.assertIsNone(integration.syncing_started_at)

    async def test_undecryptable_credentials_are_caught_and_recorded(self):
        """Phase 1 gap: _load_config used to run before the try/except that
        records failures, so a decrypt failure raised with the row never
        marked `error`. Moved inside the guarded block in Phase 2."""
        integration = self._integration()
        integration.config_json = "enc:v1:not-actually-a-valid-token"
        self.db.commit()
        with self.assertRaises(IntegrationNotConfiguredError):
            await sync_integration(self.db, integration, trigger="manual")
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.error)
        self.assertIsNotNone(integration.last_sync_error)
        self.assertIsNone(integration.syncing_started_at)

    async def test_ingest_failure_leaves_the_row_in_error_not_syncing(self):
        """A failure downstream of the fetch (cleaning, size cap, a planner
        bug) used to leave the row stuck in `syncing` forever -- nothing
        wrapped that stage before Phase 2."""
        integration = self._integration()
        with mock.patch.object(settings, "MAX_ROWS_PER_FILE", 1), mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ):
            with self.assertRaises(FileValidationError):
                await sync_integration(self.db, integration, trigger="manual")
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.error)
        self.assertIn("failed while processing", integration.last_sync_error)
        self.assertIsNone(integration.syncing_started_at)

    async def test_concurrent_sync_is_rejected_without_touching_the_row(self):
        integration = self._integration()
        self.assertTrue(claim_integration_for_sync(self.db, integration.id))
        self.db.refresh(integration)
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ) as fetch:
            with self.assertRaises(IntegrationSyncInProgressError):
                await sync_integration(self.db, integration, trigger="scheduled")
            fetch.assert_not_called()

    async def test_first_sync_blocked_by_plan_limit_never_fetches(self):
        integration = self._integration()
        with mock.patch(
            "services.integration_sync.assert_upload_allowed",
            side_effect=HTTPException(403, {"code": "plan_limit", "message": "Upgrade to sync more."}),
        ), mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ) as fetch:
            with self.assertRaises(IntegrationNotConfiguredError) as ctx:
                await sync_integration(self.db, integration, trigger="manual")
            fetch.assert_not_called()
        self.assertIn("Upgrade to sync", str(ctx.exception))
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.error)
        self.assertEqual(integration.last_sync_error, "Upgrade to sync more.")

    async def test_resync_never_checks_the_upload_quota(self):
        """Only the first sync creates a new Upload row; a refresh reuses it,
        so it must not be blocked by an upload cap."""
        integration = self._integration()
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ):
            await sync_integration(self.db, integration, trigger="manual")

        with mock.patch(
            "services.integration_sync.assert_upload_allowed",
            side_effect=HTTPException(403, {"code": "plan_limit", "message": "blocked"}),
        ) as quota, mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ):
            result = await sync_integration(self.db, integration, trigger="scheduled")
        quota.assert_not_called()
        self.assertEqual(result["integration"]["status"], "active")

    async def test_auto_analyze_skip_reason_is_surfaced_not_swallowed(self):
        integration = self._integration(auto_analyze=1)
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ), mock.patch(
            "services.integration_analysis.assert_analysis_allowed",
            side_effect=HTTPException(403, {"code": "plan_limit", "message": "Analysis cap reached."}),
        ):
            result = await sync_integration(self.db, integration, trigger="manual")
        self.assertIsNone(result["analysis_id"])
        self.assertEqual(result["analysis_skipped_reason"], "Analysis cap reached.")
        # The sync itself must still be a full success.
        self.assertEqual(result["integration"]["status"], "active")

    async def test_unknown_provider_raises_without_claiming(self):
        integration = self._integration(provider="not_a_real_provider")
        with self.assertRaises(IntegrationFetchError):
            await sync_integration(self.db, integration, trigger="manual")
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.pending)

    async def test_a_stale_syncing_row_can_be_reclaimed_and_synced(self):
        """A row left in `syncing` by a crashed process is not just claimable
        in isolation (see ClaimIntegrationForSyncTests) -- a real sync must be
        able to run to completion on it end to end."""
        stale = datetime.utcnow() - timedelta(
            minutes=settings.INTEGRATION_STALE_SYNC_MINUTES + 5
        )
        integration = self._integration(
            status=IntegrationStatus.syncing, syncing_started_at=stale
        )
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ):
            await sync_integration(self.db, integration, trigger="scheduled")
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.active)

    async def test_an_arbitrary_ingest_exception_still_leaves_the_row_in_error(self):
        """Not just the size cap: ANY failure downstream of the fetch -- a bug
        in cleaning, profiling, or planning -- must not strand the row. This
        deliberately uses a generic exception unrelated to any specific
        validation rule, to prove the containment isn't narrowly scoped to
        FileValidationError."""
        integration = self._integration()
        with mock.patch(
            "services.integration_sync.fetch_provider_data",
            new=mock.AsyncMock(return_value=self._df()),
        ), mock.patch(
            "services.integration_sync.ingest_dataframe",
            side_effect=ValueError("unexpected cleaner bug"),
        ):
            with self.assertRaises(ValueError):
                await sync_integration(self.db, integration, trigger="manual")
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.error)
        self.assertIn("unexpected cleaner bug", integration.last_sync_error)
        self.assertIsNone(integration.syncing_started_at)


class PostSyncAnalysisSkipReasonTests(unittest.TestCase):
    """run_post_sync_analysis returns (analysis_id, skipped_reason) so a plan
    limit is a visible outcome, not a silently swallowed exception."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        enable_sqlite_pragmas(cls.engine)  # FK cascade-delete needs this explicitly now
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all([User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")])
        self.db.commit()
        upload = Upload(
            id="up1", workspace_id="ws1", filename="f.csv", file_type=".csv", file_url="",
            status="completed",
        )
        self.db.add(upload)
        self.db.commit()
        # Inserted separately: datasets and data_source_integrations have a
        # genuine FK cycle (dataset.integration_id <-> integration.dataset_id),
        # which makes SQLAlchemy's automatic flush-ordering unreliable for any
        # multi-object add_all() that touches this part of the graph, even
        # when the cycle itself isn't involved. Same reason ingest_dataframe
        # flushes the upload before constructing the dataset.
        dataset = Dataset(
            id="ds1", upload_id="up1", name="f", schema_json="{}", data_summary="{}",
        )
        self.db.add(dataset)
        self.db.commit()

    def _wipe(self):
        db = self.Session()
        try:
            db.query(Dataset).delete()
            db.query(Upload).delete()
            db.query(Workspace).delete()
            db.query(User).delete()
            db.commit()
        finally:
            db.close()

    def test_missing_dataset_returns_a_reason_not_a_silent_none(self):
        from services.integration_analysis import run_post_sync_analysis

        ghost = Dataset(id="ghost", upload_id="up1", name="g")
        analysis_id, reason = run_post_sync_analysis(self.db, "wrong-workspace", ghost)
        self.assertIsNone(analysis_id)
        self.assertIsNotNone(reason)

    def test_plan_limit_message_is_returned_verbatim(self):
        from services.integration_analysis import run_post_sync_analysis

        dataset = self.db.query(Dataset).filter(Dataset.id == "ds1").first()
        with mock.patch(
            "services.integration_analysis.assert_analysis_allowed",
            side_effect=HTTPException(403, {"code": "plan_limit", "message": "At your cap."}),
        ):
            analysis_id, reason = run_post_sync_analysis(self.db, "ws1", dataset)
        self.assertIsNone(analysis_id)
        self.assertEqual(reason, "At your cap.")

    def test_successful_analysis_returns_id_and_no_reason(self):
        from services.integration_analysis import run_post_sync_analysis

        dataset = self.db.query(Dataset).filter(Dataset.id == "ds1").first()
        fake_result = {"executive_summary": "ok", "top_priorities": []}
        with mock.patch(
            "services.integration_analysis._ai_analyzer"
        ) as ai:
            ai.analyze.return_value = fake_result
            analysis_id, reason = run_post_sync_analysis(self.db, "ws1", dataset)
        self.assertIsNotNone(analysis_id)
        self.assertIsNone(reason)


class GoogleOauthUrlTests(unittest.TestCase):
    """The authorize URL is where Google decides whether this connection can
    ever refresh itself. Getting the parameters wrong produces a source that
    works for an hour and then dies."""

    def setUp(self):
        for key, value in (
            ("GOOGLE_CLIENT_ID", "test-client-id"),
            ("GOOGLE_CLIENT_SECRET", "test-secret"),
            ("GOOGLE_REDIRECT_URI", "https://api.example.com/api/integrations/oauth/callback/google"),
        ):
            patcher = mock.patch.object(settings, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_configured_flag_requires_all_three_settings(self):
        self.assertTrue(gsvc.google_oauth_configured())
        for key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
            with self.subTest(missing=key), mock.patch.object(settings, key, ""):
                self.assertFalse(gsvc.google_oauth_configured())

    def test_authorize_url_asks_for_offline_access_and_consent(self):
        """Without access_type=offline Google issues no refresh token at all,
        and without prompt=consent a repeat connect silently omits it -- either
        way the source cannot survive its first hour."""
        url = gsvc.build_google_authorize_url("STATE123")
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", gsvc.AUTHORIZE_URL)
        self.assertEqual(params["access_type"], ["offline"])
        self.assertEqual(params["prompt"], ["consent"])
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["state"], ["STATE123"])
        self.assertEqual(params["client_id"], ["test-client-id"])

    def test_authorize_url_requests_drive_read_scope(self):
        params = parse_qs(urlparse(gsvc.build_google_authorize_url("s")).query)
        self.assertIn("https://www.googleapis.com/auth/drive.readonly", params["scope"][0])


class GoogleTokenPayloadTests(unittest.TestCase):
    """Google's refresh response omits the refresh token. Treating the payload
    as a replacement rather than a merge would erase the only credential that
    lets the connection renew itself."""

    def test_first_exchange_stores_both_tokens_and_an_expiry(self):
        config: dict = {}
        gsvc._apply_token_payload(
            config,
            {"access_token": "at1", "refresh_token": "rt1", "expires_in": 3600},
        )
        self.assertEqual(config["access_token"], "at1")
        self.assertEqual(config["refresh_token"], "rt1")
        self.assertIn("access_token_expires_at", config)

    def test_refresh_without_a_refresh_token_preserves_the_stored_one(self):
        config = {"access_token": "at1", "refresh_token": "rt1"}
        gsvc._apply_token_payload(config, {"access_token": "at2", "expires_in": 3600})
        self.assertEqual(config["access_token"], "at2")
        self.assertEqual(config["refresh_token"], "rt1", "refresh token was lost")

    def test_a_rotated_refresh_token_is_taken_when_offered(self):
        config = {"access_token": "at1", "refresh_token": "rt1"}
        gsvc._apply_token_payload(
            config, {"access_token": "at2", "refresh_token": "rt2", "expires_in": 3600}
        )
        self.assertEqual(config["refresh_token"], "rt2")

    def test_missing_expiry_is_treated_as_expired(self):
        self.assertTrue(gsvc._token_expired({}))

    def test_an_expiry_in_the_near_future_still_counts_as_expired(self):
        """Refreshed slightly early so a token cannot lapse mid-request."""
        soon = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
        self.assertTrue(gsvc._token_expired({"access_token_expires_at": soon}))

    def test_a_comfortably_future_expiry_is_not_expired(self):
        later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        self.assertFalse(gsvc._token_expired({"access_token_expires_at": later}))

    def test_unparseable_expiry_is_treated_as_expired(self):
        self.assertTrue(gsvc._token_expired({"access_token_expires_at": "not-a-date"}))


class GoogleTokenExchangeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for key, value in (
            ("GOOGLE_CLIENT_ID", "cid"),
            ("GOOGLE_CLIENT_SECRET", "sec"),
            ("GOOGLE_REDIRECT_URI", "https://api.example.com/cb"),
        ):
            patcher = mock.patch.object(settings, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _client_returning(self, *, status: int, payload=None, text=""):
        class _Resp:
            status_code = status

            def json(self):
                return payload or {}

            @property
            def text(self):
                return text

        class _Client:
            def __init__(self_inner, *a, **kw):
                pass

            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def post(self_inner, *a, **kw):
                return _Resp()

        return _Client

    async def test_exchange_without_a_refresh_token_is_refused(self):
        """Google returns no refresh token when a prior grant is still active.
        Accepting that would create a source that dies in an hour with a
        confusing error, so it fails now with an actionable one instead."""
        with mock.patch.object(
            gsvc.httpx, "AsyncClient",
            self._client_returning(status=200, payload={"access_token": "at", "expires_in": 3600}),
        ):
            with self.assertRaises(IntegrationFetchError) as ctx:
                await gsvc.google_exchange_code_for_tokens("code123")
        self.assertIn("refresh token", str(ctx.exception).lower())

    async def test_successful_exchange_returns_the_payload(self):
        payload = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        with mock.patch.object(
            gsvc.httpx, "AsyncClient", self._client_returning(status=200, payload=payload)
        ):
            self.assertEqual(await gsvc.google_exchange_code_for_tokens("code123"), payload)

    async def test_a_revoked_grant_on_refresh_says_to_reconnect(self):
        with mock.patch.object(
            gsvc.httpx, "AsyncClient",
            self._client_returning(status=400, text='{"error":"invalid_grant"}'),
        ):
            with self.assertRaises(IntegrationFetchError) as ctx:
                await gsvc.google_refresh_access_token({"refresh_token": "rt"})
        self.assertIn("reconnect", str(ctx.exception).lower())

    async def test_refresh_without_a_stored_token_fails_clearly(self):
        with self.assertRaises(IntegrationFetchError) as ctx:
            await gsvc.google_refresh_access_token({})
        self.assertIn("missing", str(ctx.exception).lower())

    async def test_unconfigured_deployment_is_a_config_error_not_a_crash(self):
        with mock.patch.object(settings, "GOOGLE_CLIENT_ID", ""):
            with self.assertRaises(IntegrationNotConfiguredError):
                await gsvc.google_ensure_access_token({"access_token": "at"})


class GoogleDownloadTests(unittest.IsolatedAsyncioTestCase):
    """A native Google Sheet has no bytes to download and must be exported;
    a genuinely uploaded file must not be. Sending either down the other's
    path fails."""

    def _capture_client(self, *, content=b"a,b\n1,2\n", status=200, content_type="text/csv"):
        seen: dict = {}

        class _Resp:
            status_code = status
            headers = {"content-type": content_type}

            @property
            def content(self):
                return content

            @property
            def text(self):
                return "error body"

        class _Client:
            def __init__(self_inner, *a, **kw):
                pass

            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def get(self_inner, url, params=None, headers=None):
                seen["url"] = url
                seen["params"] = params or {}
                return _Resp()

        return _Client, seen

    async def _download(self, config, **kw):
        client_cls, seen = self._capture_client(**kw)
        with mock.patch.object(
            gsvc, "google_ensure_access_token", new=mock.AsyncMock(return_value="tok")
        ), mock.patch.object(gsvc.httpx, "AsyncClient", client_cls):
            df = await gsvc.google_download_item_as_dataframe(config)
        return df, seen

    @staticmethod
    def _xlsx_bytes() -> bytes:
        buf = io.BytesIO()
        pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(buf, index=False)
        return buf.getvalue()

    async def test_native_sheet_uses_the_export_endpoint_as_xlsx(self):
        """CSV export would silently return only the first tab, so xlsx it is.
        Uses real workbook bytes so the exported payload is actually parsed,
        not just the request inspected."""
        df, seen = await self._download(
            {"item_id": "abc", "item_name": "Q4", "mime_type": gsvc.GOOGLE_SHEET_MIME},
            content=self._xlsx_bytes(),
            content_type=gsvc.XLSX_MIME,
        )
        self.assertTrue(seen["url"].endswith("/files/abc/export"))
        self.assertEqual(seen["params"]["mimeType"], gsvc.XLSX_MIME)
        self.assertEqual(list(df.columns), ["a", "b"])
        self.assertEqual(len(df), 2)

    async def test_uploaded_file_uses_alt_media_not_export(self):
        df, seen = await self._download(
            {"item_id": "abc", "item_name": "data.csv", "mime_type": "text/csv"}
        )
        self.assertTrue(seen["url"].endswith("/files/abc"))
        self.assertEqual(seen["params"]["alt"], "media")
        self.assertNotIn("export", seen["url"])
        self.assertEqual(list(df.columns), ["a", "b"])

    async def test_shared_drive_files_are_reachable(self):
        """A sheet living in someone else's Drive is a normal way teams share."""
        _, seen = await self._download(
            {"item_id": "abc", "item_name": "data.csv", "mime_type": "text/csv"}
        )
        self.assertEqual(seen["params"].get("supportsAllDrives"), "true")

    async def test_no_selected_file_is_a_config_error(self):
        with self.assertRaises(IntegrationNotConfiguredError):
            await self._download({"item_name": "x"})

    async def test_revoked_access_says_to_reconnect(self):
        with self.assertRaises(IntegrationFetchError) as ctx:
            await self._download(
                {"item_id": "abc", "mime_type": "text/csv"}, status=403
            )
        self.assertIn("reconnect", str(ctx.exception).lower())

    async def test_deleted_file_reports_that_specifically(self):
        with self.assertRaises(IntegrationFetchError) as ctx:
            await self._download(
                {"item_id": "abc", "mime_type": "text/csv"}, status=404
            )
        self.assertIn("no longer exists", str(ctx.exception).lower())

    async def test_an_html_login_page_is_not_parsed_as_data(self):
        """Same class of bug as the export-URL sniffer: a redirect to a sign-in
        page must not become an empty one-column dataset."""
        with self.assertRaises(IntegrationFetchError) as ctx:
            await self._download(
                {"item_id": "abc", "mime_type": "text/csv"},
                content=b"\n  <html><body>Sign in</body></html>",
                content_type="text/html",
            )
        self.assertIn("web page", str(ctx.exception).lower())


class GoogleFileListingTests(unittest.IsolatedAsyncioTestCase):
    async def _list(self, files):
        payload = {"files": files}

        with mock.patch.object(
            gsvc, "google_ensure_access_token", new=mock.AsyncMock(return_value="tok")
        ), mock.patch.object(
            gsvc, "_drive_get_json", new=mock.AsyncMock(return_value=payload)
        ) as drive:
            result = await gsvc.google_list_spreadsheets({})
        return result, drive

    async def test_native_sheets_are_flagged_so_download_can_branch(self):
        result, _ = await self._list(
            [
                {"id": "1", "name": "Native", "mimeType": gsvc.GOOGLE_SHEET_MIME},
                {"id": "2", "name": "Upload.xlsx", "mimeType": gsvc.XLSX_MIME},
            ]
        )
        by_id = {r["id"]: r for r in result}
        self.assertTrue(by_id["1"]["is_native_sheet"])
        self.assertFalse(by_id["2"]["is_native_sheet"])

    async def test_query_restricts_to_spreadsheets_and_excludes_trash(self):
        _, drive = await self._list([])
        params = drive.await_args.kwargs["params"]
        self.assertIn(gsvc.GOOGLE_SHEET_MIME, params["q"])
        self.assertIn("trashed=false", params["q"])

    async def test_listing_includes_shared_drives(self):
        _, drive = await self._list([])
        params = drive.await_args.kwargs["params"]
        self.assertEqual(params["includeItemsFromAllDrives"], "true")
        self.assertEqual(params["supportsAllDrives"], "true")

    async def test_entries_without_an_id_are_skipped(self):
        result, _ = await self._list([{"name": "no id"}, {"id": "1", "name": "ok"}])
        self.assertEqual([r["id"] for r in result], ["1"])


class GoogleMultiConnectRouteTests(unittest.TestCase):
    """POST /oauth/complete/google, exercised through the real router.

    This is the endpoint that lets one Google sign-in connect several sheets
    at once, so the batching rules -- capacity checked for the whole selection,
    per-file naming, no inline syncing -- are the behaviour worth pinning.
    """

    @classmethod
    def setUpClass(cls):
        from sqlalchemy.pool import StaticPool

        # TestClient serves the request on its own thread while the assertions
        # run on this one. StaticPool keeps every thread on the same in-memory
        # database (a fresh connection would otherwise get an empty one), and
        # check_same_thread=False lets that single connection cross threads.
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
        from routes import integrations as routes_integrations

        for key, value in (
            ("INTEGRATIONS_ENABLED", True),
            ("INTEGRATION_CREDENTIALS_KEY", ""),
            ("INTEGRATION_MAX_PER_WORKSPACE", 10),
        ):
            patcher = mock.patch.object(settings, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        creds._cipher_cache = None
        self.addCleanup(setattr, creds, "_cipher_cache", None)

        # The initial sync is a background task; it would otherwise fire real
        # provider calls after the response. What it does is covered by
        # SyncIntegrationEndToEndTests.
        sync_patcher = mock.patch.object(
            routes_integrations, "_sync_new_integrations", new=mock.AsyncMock()
        )
        self.mock_bg_sync = sync_patcher.start()
        self.addCleanup(sync_patcher.stop)

        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.user = User(id="u1", email="o@x.com")
        self.db.add_all(
            [self.user, Workspace(id="ws1", name="W", owner_id="u1")]
        )
        self.db.commit()

        # A router-only app: mounting main.app would drag in the lifespan
        # (migrations, backfills) which has nothing to do with this route.
        app = FastAPI()
        app.include_router(routes_integrations.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_active_workspace] = lambda: (self.user, "ws1")
        self.client = TestClient(app)

    def _wipe(self):
        db = self.Session()
        try:
            for model in (DataSourceIntegration, IntegrationOauthSession, Workspace, User):
                db.query(model).delete()
            db.commit()
        finally:
            db.close()

    def _session_with(self, files):
        return oauth.create_oauth_session(
            self.db,
            {
                "provider": "google_sheets",
                "workspace_id": "ws1",
                "user_email": "o@x.com",
                "name": "",
                "refresh_interval_hours": 24,
                "auto_analyze": True,
                "dashboard_plan_locked": True,
                "config": {"access_token": "at", "refresh_token": "rt"},
                "files": files,
            },
        )

    @staticmethod
    def _files(n):
        return [
            {
                "id": f"f{i}",
                "name": f"Sheet {i}.xlsx",
                "mime_type": gsvc.GOOGLE_SHEET_MIME,
                "web_url": f"https://docs.google.com/{i}",
            }
            for i in range(1, n + 1)
        ]

    def _post(self, session_id, item_ids):
        return self.client.post(
            "/api/integrations/oauth/complete/google",
            json={"session_id": session_id, "item_ids": item_ids},
        )

    def test_connecting_several_sheets_creates_one_source_each(self):
        sid = self._session_with(self._files(3))
        resp = self._post(sid, ["f1", "f2", "f3"])
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["connected"], 3)
        self.assertEqual(self.db.query(DataSourceIntegration).count(), 3)

    def test_each_source_is_named_after_its_own_file(self):
        """One display name across a multi-select would make three identical
        rows the user cannot tell apart."""
        sid = self._session_with(self._files(2))
        body = self._post(sid, ["f1", "f2"]).json()
        self.assertEqual(
            sorted(i["name"] for i in body["integrations"]),
            ["Sheet 1.xlsx", "Sheet 2.xlsx"],
        )

    def test_sources_start_pending_and_sync_in_the_background(self):
        """Syncing several sheets inline would hold the request open for
        minutes; the client polls instead."""
        sid = self._session_with(self._files(2))
        body = self._post(sid, ["f1", "f2"]).json()
        self.assertTrue(body["syncing"])
        self.assertEqual({i["status"] for i in body["integrations"]}, {"pending"})
        self.mock_bg_sync.assert_called_once()

    def test_each_source_stores_its_own_file_reference(self):
        sid = self._session_with(self._files(2))
        self._post(sid, ["f1", "f2"])
        stored = {
            decrypt_config(r.config_json)["item_id"]
            for r in self.db.query(DataSourceIntegration).all()
        }
        self.assertEqual(stored, {"f1", "f2"})

    def test_the_shared_google_credentials_reach_every_source(self):
        sid = self._session_with(self._files(2))
        self._post(sid, ["f1", "f2"])
        for row in self.db.query(DataSourceIntegration).all():
            cfg = decrypt_config(row.config_json)
            self.assertEqual(cfg["refresh_token"], "rt")

    def test_a_single_selection_keeps_the_users_chosen_name(self):
        sid = oauth.create_oauth_session(
            self.db,
            {
                "provider": "google_sheets",
                "workspace_id": "ws1",
                "user_email": "o@x.com",
                "name": "Q4 revenue",
                "refresh_interval_hours": 24,
                "auto_analyze": True,
                "dashboard_plan_locked": True,
                "config": {"access_token": "at", "refresh_token": "rt"},
                "files": self._files(2),
            },
        )
        body = self._post(sid, ["f1"]).json()
        self.assertEqual(body["integrations"][0]["name"], "Q4 revenue")

    def test_a_batch_that_would_exceed_the_cap_is_refused_atomically(self):
        """Connecting some-but-not-all would leave the user guessing which
        landed, so the whole batch is checked before anything is created."""
        with mock.patch.object(settings, "INTEGRATION_MAX_PER_WORKSPACE", 2):
            sid = self._session_with(self._files(3))
            resp = self._post(sid, ["f1", "f2", "f3"])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("exceed the limit", resp.json()["detail"])
        self.assertEqual(self.db.query(DataSourceIntegration).count(), 0)

    def test_the_cap_counts_sources_already_connected(self):
        with mock.patch.object(settings, "INTEGRATION_MAX_PER_WORKSPACE", 2):
            self.db.add(
                DataSourceIntegration(
                    workspace_id="ws1", provider="stripe", name="existing",
                    connection_mode="api_key", refresh_interval_hours=24,
                    status=IntegrationStatus.active,
                )
            )
            self.db.commit()
            sid = self._session_with(self._files(2))
            resp = self._post(sid, ["f1", "f2"])
        self.assertEqual(resp.status_code, 400)
        self.assertIn("1 already connected", resp.json()["detail"])

    def test_a_file_not_in_the_sign_in_is_rejected(self):
        """Guards against a client posting an arbitrary Drive id that the
        consent screen never showed."""
        sid = self._session_with(self._files(2))
        resp = self._post(sid, ["f1", "not-mine"])
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.db.query(DataSourceIntegration).count(), 0)

    def test_the_session_is_single_use(self):
        sid = self._session_with(self._files(2))
        self.assertEqual(self._post(sid, ["f1"]).status_code, 200)
        self.assertEqual(self._post(sid, ["f2"]).status_code, 404)

    def test_another_workspaces_session_is_refused(self):
        sid = oauth.create_oauth_session(
            self.db,
            {
                "provider": "google_sheets",
                "workspace_id": "ws1",
                "user_email": "someone-else@x.com",
                "name": "",
                "refresh_interval_hours": 24,
                "auto_analyze": True,
                "dashboard_plan_locked": True,
                "config": {},
                "files": self._files(1),
            },
        )
        self.assertEqual(self._post(sid, ["f1"]).status_code, 403)

    def test_an_empty_selection_is_rejected_by_validation(self):
        sid = self._session_with(self._files(1))
        self.assertEqual(self._post(sid, []).status_code, 422)

    def test_the_route_is_gated_by_the_feature_flag(self):
        sid = self._session_with(self._files(1))
        with mock.patch.object(settings, "INTEGRATIONS_ENABLED", False):
            self.assertEqual(self._post(sid, ["f1"]).status_code, 503)


class GoogleChangeStampTests(unittest.IsolatedAsyncioTestCase):
    """The cheap freshness probe. It must never be the reason a sync fails --
    it is an optimisation, so anything unexpected has to fall through to a
    normal sync rather than break a working connection."""

    async def test_returns_the_remote_modified_time(self):
        with mock.patch.object(
            gsvc, "google_ensure_access_token", new=mock.AsyncMock(return_value="tok")
        ), mock.patch.object(
            gsvc,
            "_drive_get_json",
            new=mock.AsyncMock(return_value={"modifiedTime": "2026-01-01T00:00:00Z"}),
        ):
            stamp = await gsvc.google_remote_change_stamp({"item_id": "abc"})
        self.assertEqual(stamp, "2026-01-01T00:00:00Z")

    async def test_probe_asks_only_for_the_timestamp(self):
        """The point is that this is cheap; pulling the whole file record back
        would defeat it."""
        with mock.patch.object(
            gsvc, "google_ensure_access_token", new=mock.AsyncMock(return_value="tok")
        ), mock.patch.object(
            gsvc, "_drive_get_json", new=mock.AsyncMock(return_value={})
        ) as drive:
            await gsvc.google_remote_change_stamp({"item_id": "abc"})
        self.assertEqual(drive.await_args.kwargs["params"]["fields"], "modifiedTime")

    async def test_no_selected_file_yields_no_stamp(self):
        self.assertIsNone(await gsvc.google_remote_change_stamp({}))

    async def test_a_failing_probe_is_swallowed_not_raised(self):
        with mock.patch.object(
            gsvc,
            "google_ensure_access_token",
            new=mock.AsyncMock(side_effect=IntegrationFetchError("token dead")),
        ):
            self.assertIsNone(await gsvc.google_remote_change_stamp({"item_id": "abc"}))

    async def test_a_response_without_a_timestamp_yields_no_stamp(self):
        with mock.patch.object(
            gsvc, "google_ensure_access_token", new=mock.AsyncMock(return_value="tok")
        ), mock.patch.object(
            gsvc, "_drive_get_json", new=mock.AsyncMock(return_value={})
        ):
            self.assertIsNone(await gsvc.google_remote_change_stamp({"item_id": "abc"}))

    async def test_dispatcher_returns_none_for_providers_without_a_probe(self):
        for provider, mode in (
            ("stripe", "api_key"),
            ("excel_onedrive", "oauth"),
            ("google_sheets", "export_url"),
        ):
            with self.subTest(provider=provider):
                self.assertIsNone(await conn.remote_change_stamp(provider, mode, {}))


class UnchangedSourceSkipTests(unittest.IsolatedAsyncioTestCase):
    """A scheduled refresh of a source nobody edited should cost one metadata
    call, not a full download-clean-recache cycle."""

    @classmethod
    def setUpClass(cls):
        # A real (non-skipped) sync offloads ingest_dataframe onto a worker
        # thread, so this engine is used from a thread other than the one that
        # created it -- same reason SyncIntegrationEndToEndTests overrides
        # check_same_thread.
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        enable_sqlite_pragmas(cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        import tempfile

        # These exercise the scheduling machinery itself, so they opt into
        # unattended syncing; it is off by default (see ManualOnlySyncTests).
        auto = mock.patch.object(settings, "INTEGRATION_AUTO_SYNC_ENABLED", True)
        auto.start()
        self.addCleanup(auto.stop)

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        for key, value in (
            ("UPLOAD_DIR", self._tmpdir.name),
            ("INTEGRATION_CREDENTIALS_KEY", ""),
        ):
            patcher = mock.patch.object(settings, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        creds._cipher_cache = None
        self.addCleanup(setattr, creds, "_cipher_cache", None)

        llm = mock.patch("services.ingest_pipeline.propose_column_roles")
        m = llm.start()
        m.return_value = {"roles": {}, "meanings": {}, "source": "auto"}
        self.addCleanup(llm.stop)

        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all([User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")])
        self.db.commit()

    def _wipe(self):
        db = self.Session()
        try:
            for model in (Dataset, Upload, DataSourceIntegration, Workspace, User):
                db.query(model).delete()
            db.commit()
        finally:
            db.close()

    def _df(self):
        return pd.DataFrame(
            {
                "order_date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "revenue": [10.0, 20.0],
            }
        )

    def _integration(self, **cfg):
        base = {"access_token": "at", "refresh_token": "rt", "item_id": "abc"}
        base.update(cfg)
        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="google_sheets",
            name="Q4 sheet",
            connection_mode="oauth",
            config_json=creds.encrypt_config(base),
            refresh_interval_hours=24,
            status=IntegrationStatus.active,
            next_sync_at=datetime.utcnow(),
            auto_analyze=0,
            dataset_id=None,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    async def _sync(self, integration, *, trigger, stamp, fetch=None):
        fetch_mock = fetch or mock.AsyncMock(return_value=self._df())
        with mock.patch(
            "services.integration_sync.remote_change_stamp",
            new=mock.AsyncMock(return_value=stamp),
        ), mock.patch(
            "services.integration_sync.fetch_provider_data", new=fetch_mock
        ):
            result = await sync_integration(self.db, integration, trigger=trigger)
        return result, fetch_mock

    async def test_scheduled_sync_of_an_unchanged_source_does_not_download(self):
        integration = self._integration(last_change_stamp="STAMP-1")
        result, fetch = await self._sync(integration, trigger="scheduled", stamp="STAMP-1")
        fetch.assert_not_called()
        self.assertTrue(result["skipped"])
        self.assertEqual(self.db.query(Dataset).count(), 0)

    async def test_a_skipped_sync_leaves_the_source_healthy_and_rescheduled(self):
        integration = self._integration(last_change_stamp="STAMP-1")
        before = integration.next_sync_at
        await self._sync(integration, trigger="scheduled", stamp="STAMP-1")
        self.db.refresh(integration)
        self.assertEqual(integration.status, IntegrationStatus.active)
        self.assertIsNone(integration.syncing_started_at)
        self.assertIsNone(integration.last_sync_error)
        self.assertGreater(integration.next_sync_at, before)

    async def test_a_skipped_sync_does_not_move_last_sync_at(self):
        """last_sync_at is what the UI shows as 'data as of'. Bumping it when
        no data moved would tell the user something arrived that didn't."""
        integration = self._integration(last_change_stamp="STAMP-1")
        integration.last_sync_at = datetime(2026, 1, 1, 12, 0, 0)
        self.db.commit()
        await self._sync(integration, trigger="scheduled", stamp="STAMP-1")
        self.db.refresh(integration)
        self.assertEqual(integration.last_sync_at, datetime(2026, 1, 1, 12, 0, 0))

    async def test_a_changed_source_is_downloaded(self):
        integration = self._integration(last_change_stamp="STAMP-1")
        result, fetch = await self._sync(integration, trigger="scheduled", stamp="STAMP-2")
        fetch.assert_called_once()
        self.assertFalse(result["skipped"])

    async def test_the_new_stamp_is_remembered_after_a_real_sync(self):
        integration = self._integration(last_change_stamp="STAMP-1")
        await self._sync(integration, trigger="scheduled", stamp="STAMP-2")
        self.db.refresh(integration)
        self.assertEqual(decrypt_config(integration.config_json)["last_change_stamp"], "STAMP-2")

    async def test_a_manual_refresh_never_skips(self):
        """Someone who clicks Refresh gets a real fetch: 'nothing happened' is
        a worse answer than doing the work."""
        integration = self._integration(last_change_stamp="STAMP-1")
        result, fetch = await self._sync(integration, trigger="manual", stamp="STAMP-1")
        fetch.assert_called_once()
        self.assertFalse(result["skipped"])

    async def test_a_first_sync_never_skips(self):
        """Nothing has been stored yet, so there is nothing to compare against."""
        integration = self._integration()
        result, fetch = await self._sync(integration, trigger="scheduled", stamp="STAMP-1")
        fetch.assert_called_once()
        self.assertFalse(result["skipped"])

    async def test_an_unavailable_probe_falls_through_to_a_real_sync(self):
        """Providers with no cheap probe, and failed probes, both report None.
        Neither may be treated as 'unchanged'."""
        integration = self._integration(last_change_stamp="STAMP-1")
        result, fetch = await self._sync(integration, trigger="scheduled", stamp=None)
        fetch.assert_called_once()
        self.assertFalse(result["skipped"])


class ManualOnlySyncTests(unittest.TestCase):
    """Sources must not refresh on their own unless that is switched on.

    An unattended refresh spends money -- provider calls, model calls, storage
    writes -- with nobody watching, and it does so per connected source per
    cycle. The default is therefore manual-only, protected in three independent
    places so that turning it on has to be deliberate: nothing is written as
    due, nothing is found as due, and the cron endpoint does nothing.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        enable_sqlite_pragmas(cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self._wipe)
        self.db.add_all(
            [User(id="u1", email="o@x.com"), Workspace(id="ws1", name="W", owner_id="u1")]
        )
        self.db.commit()

    def _wipe(self):
        db = self.Session()
        try:
            for model in (DataSourceIntegration, Workspace, User):
                db.query(model).delete()
            db.commit()
        finally:
            db.close()

    def _add_overdue(self) -> DataSourceIntegration:
        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="google_sheets",
            name="s",
            connection_mode="oauth",
            refresh_interval_hours=24,
            status=IntegrationStatus.active,
            next_sync_at=datetime.utcnow() - timedelta(days=7),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def test_manual_only_is_the_default(self):
        """Nobody should have to remember to switch this off."""
        from config import Settings

        self.assertFalse(Settings().INTEGRATION_AUTO_SYNC_ENABLED)

    def test_new_sources_are_not_given_a_due_date(self):
        from services.integration_sync import initial_next_sync_at, next_sync_at_for

        self.assertIsNone(initial_next_sync_at())
        self.assertIsNone(next_sync_at_for(24))

    def test_a_completed_sync_does_not_book_the_next_one(self):
        from services.integration_sync import next_sync_at_for

        self.assertIsNone(next_sync_at_for(24, datetime(2026, 1, 1, 12, 0, 0)))

    def test_rows_already_marked_due_are_still_never_picked_up(self):
        """The important one: rows written while auto-sync was on, or before
        the switch existed, must not fire the moment a scheduler appears."""
        self._add_overdue()
        self.assertEqual(find_due_integrations(self.db), [])

    def test_the_same_rows_are_found_once_auto_sync_is_enabled(self):
        """Proves the previous test is the switch working, not an empty query."""
        self._add_overdue()
        with mock.patch.object(settings, "INTEGRATION_AUTO_SYNC_ENABLED", True):
            self.assertEqual(len(find_due_integrations(self.db)), 1)

    def test_scheduler_pass_syncs_nothing(self):
        import asyncio

        from services.integration_scheduler import run_due_syncs_once

        self._add_overdue()
        with mock.patch(
            "services.integration_sync.fetch_provider_data", new=mock.AsyncMock()
        ) as fetch:
            synced = asyncio.run(run_due_syncs_once())
        self.assertEqual(synced, 0)
        fetch.assert_not_called()

    def test_a_manual_refresh_is_unaffected(self):
        """Manual refresh is the whole point of manual-only mode: it must still
        claim the row and run."""
        from services.integration_sync import claim_integration_for_sync

        row = self._add_overdue()
        self.assertTrue(claim_integration_for_sync(self.db, row.id))

    def test_scheduling_settings_are_reported_as_off(self):
        from services.integration_sync import auto_sync_enabled

        self.assertFalse(auto_sync_enabled())
        with mock.patch.object(settings, "INTEGRATION_AUTO_SYNC_ENABLED", True):
            self.assertTrue(auto_sync_enabled())


class WaveGatingTests(unittest.TestCase):
    """Which providers are on offer, so a wave can ship without dragging every
    built-but-unreviewed connector live with it.

    Enforced server-side rather than hidden in the client: the catalog and the
    connect endpoints consult the same setting, so a request made by hand gets
    the same answer the button would.
    """

    def test_the_default_wave_is_the_two_spreadsheet_providers(self):
        from config import Settings

        raw = Settings().INTEGRATION_ENABLED_PROVIDERS
        self.assertEqual(
            {p.strip() for p in raw.split(",")},
            {"excel_onedrive", "google_sheets"},
        )

    def test_catalog_reports_off_wave_providers_as_unavailable(self):
        catalog = {p["id"]: p for p in list_catalog()}
        for provider_id in ("stripe", "hubspot", "ga4", "meta_ads", "shopify"):
            with self.subTest(provider=provider_id):
                modes = [
                    m["id"]
                    for m in catalog[provider_id]["connection_modes"]
                    if m.get("available", True)
                ]
                self.assertEqual(modes, [])

    def test_off_wave_providers_stay_visible_as_roadmap(self):
        """Hidden and unavailable are different: the catalog is also how users
        see what is coming."""
        catalog_ids = {p["id"] for p in list_catalog()}
        self.assertIn("stripe", catalog_ids)
        self.assertEqual(catalog_ids, {p["id"] for p in PROVIDERS})

    def test_wave_one_providers_remain_connectable(self):
        catalog = {p["id"]: p for p in list_catalog()}
        for provider_id in ("excel_onedrive", "google_sheets"):
            with self.subTest(provider=provider_id):
                modes = [
                    m["id"]
                    for m in catalog[provider_id]["connection_modes"]
                    if m.get("available", True)
                ]
                self.assertIn("oauth", modes)

    def test_an_empty_setting_means_no_wave_restriction(self):
        """So a later "everything on" does not need a code change."""
        from services.integration_registry import provider_enabled

        with mock.patch.object(settings, "INTEGRATION_ENABLED_PROVIDERS", ""):
            self.assertTrue(provider_enabled("stripe"))
            catalog = {p["id"]: p for p in list_catalog()}
            modes = [
                m["id"]
                for m in catalog["stripe"]["connection_modes"]
                if m.get("available", True)
            ]
            self.assertEqual(modes, ["api_key"])

    def test_a_wave_can_be_widened_by_configuration_alone(self):
        with mock.patch.object(
            settings, "INTEGRATION_ENABLED_PROVIDERS", "google_sheets,stripe"
        ):
            catalog = {p["id"]: p for p in list_catalog()}
            stripe_modes = [
                m["id"]
                for m in catalog["stripe"]["connection_modes"]
                if m.get("available", True)
            ]
            onedrive_modes = [
                m["id"]
                for m in catalog["excel_onedrive"]["connection_modes"]
                if m.get("available", True)
            ]
        self.assertEqual(stripe_modes, ["api_key"])
        self.assertEqual(onedrive_modes, [], "dropping a provider must also take effect")

    def test_connecting_an_off_wave_provider_is_refused(self):
        """The check that matters: the UI hiding a button is not a control."""
        from routes.integrations import _validate_connection_mode

        with self.assertRaises(Exception) as ctx:
            _validate_connection_mode("stripe", "api_key")
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)

    def test_a_wave_one_provider_still_validates(self):
        from routes.integrations import _validate_connection_mode

        _validate_connection_mode("google_sheets", "oauth")


class FrontendRedirectUrlGuardTests(unittest.TestCase):
    """FRONTEND_APP_URL is where the browser is sent after a provider sign-in.

    Left at its development default it points at the user's own machine, so a
    production connect completes on the server and then strands the user on a
    dead localhost page -- everything looks healthy in the logs. It defaults to
    localhost for local work, which makes forgetting to set it the easy
    mistake, so production refuses to boot on it rather than failing silently
    at the one moment a user is trying to connect something.
    """

    def _errors(self, url: str) -> list[str]:
        from config import Settings, collect_runtime_setting_errors

        errs = collect_runtime_setting_errors(
            Settings(APP_ENV="production", FRONTEND_APP_URL=url)
        )
        return [e for e in errs if "FRONTEND_APP_URL" in e]

    def test_the_development_default_blocks_production_boot(self):
        self.assertTrue(self._errors("http://localhost:3000"))

    def test_loopback_ip_is_caught_too(self):
        self.assertTrue(self._errors("http://127.0.0.1:3000"))

    def test_empty_blocks_production_boot(self):
        self.assertTrue(self._errors(""))

    def test_plain_http_is_rejected(self):
        """The handoff puts a session id in the query string."""
        self.assertTrue(self._errors("http://snaptix.ai"))

    def test_a_real_https_origin_is_accepted(self):
        self.assertEqual(self._errors("https://snaptix.ai"), [])

    def test_development_is_unaffected(self):
        from config import Settings, collect_runtime_setting_errors

        self.assertEqual(
            collect_runtime_setting_errors(
                Settings(APP_ENV="development", FRONTEND_APP_URL="http://localhost:3000")
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
