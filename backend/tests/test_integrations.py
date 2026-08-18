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

import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from database import Base
from models.models import (
    DataSourceIntegration,
    IntegrationStatus,
    User,
    Workspace,
)
from services import integration_connectors as conn
from services import integration_credentials as creds
from services import integration_oauth as oauth
from services.integration_connectors import (
    IntegrationFetchError,
    IntegrationNotConfiguredError,
)
from services.integration_registry import PROVIDERS, get_provider, list_catalog
from services.integration_sync import (
    compute_next_sync_at,
    find_due_integrations,
    integration_to_dict,
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
        """A login/consent page is the most common failure; it must not parse as data."""
        for body in (
            b"<!DOCTYPE html><html>...",
            b"<html><body>Sign in</body></html>",
        ):
            with self.subTest(body=body[:20]), self.assertRaises(IntegrationFetchError) as ctx:
                conn._dataframe_from_bytes(body, "https://x/y.csv", "text/html")
            self.assertIn("web page", str(ctx.exception).lower())

    def test_leading_whitespace_hides_html_from_the_sniffer(self):
        """Current behaviour, and a known gap. The sniffer slices before it strips
        (`content[:6].lstrip()`), so leading whitespace shifts the window and the
        `<html` probe never fires. A server that emits a newline before its error
        page is handed to pandas and becomes an empty one-column dataset instead
        of the actionable "that's a web page" error. Fixed in Phase 2 by stripping
        before slicing; this expectation flips there."""
        df = conn._dataframe_from_bytes(
            b"  <html><body>Sign in</body></html>", "https://x/y.csv", "text/html"
        )
        self.assertEqual(len(df), 0)

    def test_csv_payload_parses(self):
        df = conn._dataframe_from_bytes(b"a,b\n1,2\n3,4\n", "https://x/y.csv", "text/csv")
        self.assertEqual(list(df.columns), ["a", "b"])
        self.assertEqual(len(df), 2)


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

    def _add(self, *, status: IntegrationStatus, next_sync_at, name="s") -> DataSourceIntegration:
        row = DataSourceIntegration(
            workspace_id="ws1",
            provider="google_sheets",
            name=name,
            connection_mode="export_url",
            refresh_interval_hours=24,
            status=status,
            next_sync_at=next_sync_at,
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

    def test_rows_stuck_in_syncing_are_not_reclaimed(self):
        """Current behaviour, and a known gap: a crash mid-sync leaves the row
        in `syncing` forever, where neither the scheduler nor the UI can retry
        it. Phase 2 adds a stale-lock reclaim, at which point this expectation
        flips deliberately rather than silently."""
        self._add(
            status=IntegrationStatus.syncing,
            next_sync_at=datetime.utcnow() - timedelta(days=7),
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


if __name__ == "__main__":
    unittest.main()
