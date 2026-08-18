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

import json
import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from database import Base
from models.models import (
    Dataset,
    DataSourceIntegration,
    IntegrationStatus,
    Upload,
    User,
    Workspace,
)
from services import integration_connectors as conn
from services import integration_credentials as creds
from services import integration_oauth as oauth
from services.file_validation import FileValidationError
from services.ingest_pipeline import ingest_dataframe, process_dataframe
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
    IntegrationSyncInProgressError,
)
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

    async def test_oauth_is_only_wired_for_onedrive(self):
        """Microsoft is the only finished OAuth round trip; the rest must fail loudly."""
        for provider in ("google_sheets", "google_drive", "quickbooks", "slack", "hubspot"):
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
    def setUp(self):
        oauth._oauth_sessions.clear()
        self.addCleanup(oauth._oauth_sessions.clear)

    def test_create_then_get(self):
        sid = oauth.create_oauth_session({"workspace_id": "ws1"})
        self.assertEqual(oauth.get_oauth_session(sid)["workspace_id"], "ws1")

    def test_pop_is_single_use(self):
        sid = oauth.create_oauth_session({"workspace_id": "ws1"})
        self.assertIsNotNone(oauth.pop_oauth_session(sid))
        self.assertIsNone(oauth.pop_oauth_session(sid))

    def test_unknown_session_is_none(self):
        self.assertIsNone(oauth.get_oauth_session("nope"))

    def test_sessions_expire_after_an_hour(self):
        sid = oauth.create_oauth_session({"workspace_id": "ws1"})
        stale = datetime.now(UTC) - timedelta(hours=2)
        oauth._oauth_sessions[sid]["created_at"] = stale.isoformat()
        self.assertIsNone(oauth.get_oauth_session(sid))


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
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
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
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        import tempfile

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

    Verified manually against a local Postgres 16 while writing this phase:
    20 threads racing a pending row, and 20 threads racing a stale-heartbeat
    reclaim, each produced exactly one winner. Kept skipped by default so the
    regular suite has no external dependency; point
    INTEGRATION_TEST_POSTGRES_URL at a throwaway database to re-run it.
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
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        import tempfile

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


if __name__ == "__main__":
    unittest.main()
