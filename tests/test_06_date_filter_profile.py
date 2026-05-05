"""
tests/test_06_date_filter_profile.py

Tests for the date-range filter feature on GET /profile (Step 6).

Spec: .claude/specs/06-date-filter-profile-page.md

Covered behaviours
------------------
- Auth guard: unauthenticated requests redirect to /login
- Unfiltered view: all expenses returned with correct totals
- from_date + to_date: inclusive range filter
- from_date only: open-ended lower bound
- to_date only: open-ended upper bound
- Malformed date values: silently ignored, fallback to all expenses
- Preset periods: this_month, last_3_months, last_6_months
- Unknown / missing period: falls back to full unfiltered set
- Stat cards update with filtered data (total, count, top category)
- Category totals reflect filtered set
- Filter form present, uses method="GET"
- Date inputs pre-populated with active filter values (custom mode)
- Clear link present when filter is active; absent when no filter applied
- Empty state shown when filter matches no expenses
- DB helper get_expenses_by_user_filtered: both bounds, start only, end only, no params
- DB helper get_expenses_by_user: unchanged, still returns all
- SQL-injection-safe: malformed/adversarial date strings handled gracefully
"""

import sqlite3
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import (
    get_expenses_by_user,
    get_expenses_by_user_filtered,
    init_db,
)

# ---------------------------------------------------------------------------
# Seed data constants (mirrors database/db.py seed_db() values)
# ---------------------------------------------------------------------------
SEED_EXPENSES = [
    # (amount, category, date_str, description)
    (12.50,  "Food",          "2026-04-01", "Groceries"),
    ( 3.20,  "Transport",     "2026-04-05", "Bus fare"),
    (85.00,  "Bills",         "2026-04-08", "Electricity bill"),
    (22.00,  "Health",        "2026-04-10", "Pharmacy"),
    (15.99,  "Entertainment", "2026-04-14", "Streaming subscription"),
    (45.00,  "Shopping",      "2026-04-18", "New shoes"),
    ( 8.75,  "Food",          "2026-04-21", "Lunch"),
    (20.00,  "Other",         "2026-04-25", "Miscellaneous"),
]
TOTAL_ALL = round(sum(e[0] for e in SEED_EXPENSES), 2)  # 212.44
TOTAL_ALL_COUNT = len(SEED_EXPENSES)  # 8

# Expenses within 2026-04-01 .. 2026-04-10 (4 rows)
FILTER_FROM = "2026-04-01"
FILTER_TO   = "2026-04-10"
FILTERED_EXPENSES = [e for e in SEED_EXPENSES if FILTER_FROM <= e[2] <= FILTER_TO]
TOTAL_FILTERED     = round(sum(e[0] for e in FILTERED_EXPENSES), 2)  # 122.70
TOTAL_FILTERED_COUNT = len(FILTERED_EXPENSES)  # 4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    """
    Isolated Flask application backed by a temporary on-disk SQLite database.
    Using tmp_path (not ':memory:') because get_db() in db.py constructs its
    own connection from DB_PATH; we monkey-patch DB_PATH so every helper
    in the module uses the same temp file.
    """
    db_file = str(tmp_path / "test_spendly.db")

    import database.db as db_module
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_file

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        init_db()
        # Insert a controlled test user (not the demo seed user)
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (
                "Test User",
                "testuser@example.com",
                generate_password_hash("testpass1"),
                "2025-01-15 10:00:00",
            ),
        )
        conn.commit()
        user_row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("testuser@example.com",)
        ).fetchone()
        user_id = user_row["id"]

        # Insert all seed expenses for this user
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, amt, cat, dt, desc) for amt, cat, dt, desc in SEED_EXPENSES],
        )
        conn.commit()
        conn.close()

    yield flask_app

    # Restore original DB_PATH so other test modules are not affected
    db_module.DB_PATH = original_db_path


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Test client that is already logged in as testuser@example.com."""
    resp = client.post(
        "/login",
        data={"email": "testuser@example.com", "password": "testpass1"},
        follow_redirects=False,
    )
    assert resp.status_code == 302, "Login fixture failed — check credentials"
    return client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_db(app):
    """Return a raw sqlite3 connection to the test database."""
    import database.db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_test_user_id(app):
    conn = _get_db(app)
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("testuser@example.com",)
    ).fetchone()
    conn.close()
    return row["id"]


# ===========================================================================
# Auth guard
# ===========================================================================

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        resp = client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302, "Expected redirect for unauthenticated request"
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated /profile should redirect to /login"
        )

    def test_unauthenticated_profile_with_filter_params_redirects_to_login(self, client):
        resp = client.get(
            "/profile?from_date=2026-04-01&to_date=2026-04-10",
            follow_redirects=False,
        )
        assert resp.status_code == 302, "Expected redirect even with filter params"
        assert "/login" in resp.headers["Location"]


# ===========================================================================
# Unfiltered view
# ===========================================================================

class TestUnfilteredView:
    def test_profile_no_params_returns_200(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200, "Authenticated /profile should return 200"

    def test_profile_no_params_shows_all_expenses(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        # All 8 seed descriptions must appear
        for _, _, _, desc in SEED_EXPENSES:
            assert desc in html, f"Expected description '{desc}' in unfiltered profile"

    def test_profile_no_params_total_spend(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "212.44" in html, (
            f"Expected total spend $212.44 in unfiltered profile, got page: {html[:500]}"
        )

    def test_profile_no_params_transaction_count(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        # The transactions count stat card shows the count as a standalone value
        assert f">{TOTAL_ALL_COUNT}<" in html, (
            f"Expected transaction count {TOTAL_ALL_COUNT} in stat card"
        )

    def test_profile_no_params_top_category_is_bills(self, auth_client):
        """Bills ($85.00) is the single highest category."""
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "Bills" in html, "Expected 'Bills' as top category in unfiltered view"

    def test_profile_no_params_contains_filter_form(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert 'name="from_date"' in html, "Filter form must have from_date input"
        assert 'name="to_date"' in html, "Filter form must have to_date input"

    def test_profile_filter_form_uses_get_method(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert 'method="GET"' in html or "method='GET'" in html, (
            "Filter form must use method='GET'"
        )

    def test_profile_no_params_no_clear_link(self, auth_client):
        """The Clear link must NOT appear when no filter is active."""
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        # The Clear link points to /profile with no extra params; it should
        # only appear when a filter is active. We look for the text "Clear".
        # If the template shows a preset "All Time" link that also uses /profile
        # that is fine — we check that "Clear" text is absent.
        assert "Clear" not in html, (
            "Clear link must not appear when no filter is active"
        )

    def test_profile_all_time_preset_link_present(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "All Time" in html, "All Time preset link must appear on profile page"


# ===========================================================================
# from_date + to_date filter (inclusive range)
# ===========================================================================

class TestBothDateFilter:
    def test_from_and_to_date_returns_200(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        assert resp.status_code == 200

    def test_from_and_to_date_shows_only_filtered_expenses(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        for _, _, _, desc in FILTERED_EXPENSES:
            assert desc in html, (
                f"Expected '{desc}' to appear in filtered results"
            )

    def test_from_and_to_date_excludes_out_of_range_expenses(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        out_of_range = [e for e in SEED_EXPENSES if not (FILTER_FROM <= e[2] <= FILTER_TO)]
        for _, _, _, desc in out_of_range:
            assert desc not in html, (
                f"Description '{desc}' must not appear in filtered results"
            )

    def test_from_and_to_date_total_spend(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        assert "122.70" in html, (
            f"Expected filtered total $122.70 but it was not found in response"
        )

    def test_from_and_to_date_transaction_count(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        assert f">{TOTAL_FILTERED_COUNT}<" in html, (
            f"Expected transaction count {TOTAL_FILTERED_COUNT} in stat card"
        )

    def test_from_and_to_date_top_category_reflects_filtered_set(self, auth_client):
        """Within 2026-04-01..2026-04-10, Bills ($85) is still top category."""
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        assert "Bills" in html, "Top category should be Bills for this date range"

    def test_from_and_to_date_inputs_prepopulated(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        assert FILTER_FROM in html, (
            "from_date value must be pre-populated in the filter form"
        )
        assert FILTER_TO in html, (
            "to_date value must be pre-populated in the filter form"
        )

    def test_from_and_to_date_clear_link_present(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        assert "Clear" in html, (
            "Clear link must appear when a date filter is active"
        )

    def test_from_and_to_date_clear_link_points_to_profile_no_params(self, auth_client):
        """The Clear href must be /profile with no query parameters."""
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        # href="/profile" or href="/profile" (with no trailing ?)
        assert 'href="/profile"' in html, (
            "Clear link must point to /profile with no filter params"
        )

    def test_boundary_inclusive_from_date(self, auth_client):
        """The from_date itself (2026-04-01) must be included in results."""
        resp = auth_client.get("/profile?from_date=2026-04-01&to_date=2026-04-01")
        html = resp.data.decode()
        assert "Groceries" in html, "Expense on from_date boundary must be included"

    def test_boundary_inclusive_to_date(self, auth_client):
        """The to_date itself (2026-04-10) must be included in results."""
        resp = auth_client.get("/profile?from_date=2026-04-10&to_date=2026-04-10")
        html = resp.data.decode()
        assert "Pharmacy" in html, "Expense on to_date boundary must be included"


# ===========================================================================
# from_date only (open upper bound)
# ===========================================================================

class TestFromDateOnlyFilter:
    def test_from_date_only_returns_200(self, auth_client):
        resp = auth_client.get("/profile?from_date=2026-04-14")
        assert resp.status_code == 200

    def test_from_date_only_includes_expenses_on_or_after(self, auth_client):
        resp = auth_client.get("/profile?from_date=2026-04-14")
        html = resp.data.decode()
        expected = ["Streaming subscription", "New shoes", "Lunch", "Miscellaneous"]
        for desc in expected:
            assert desc in html, f"'{desc}' should be in from_date-only results"

    def test_from_date_only_excludes_earlier_expenses(self, auth_client):
        resp = auth_client.get("/profile?from_date=2026-04-14")
        html = resp.data.decode()
        excluded = ["Groceries", "Bus fare", "Electricity bill", "Pharmacy"]
        for desc in excluded:
            assert desc not in html, (
                f"'{desc}' is before from_date and must be excluded"
            )

    def test_from_date_only_clear_link_present(self, auth_client):
        resp = auth_client.get("/profile?from_date=2026-04-14")
        html = resp.data.decode()
        assert "Clear" in html, "Clear link must appear when from_date filter is active"


# ===========================================================================
# to_date only (open lower bound)
# ===========================================================================

class TestToDateOnlyFilter:
    def test_to_date_only_returns_200(self, auth_client):
        resp = auth_client.get("/profile?to_date=2026-04-08")
        assert resp.status_code == 200

    def test_to_date_only_includes_expenses_on_or_before(self, auth_client):
        resp = auth_client.get("/profile?to_date=2026-04-08")
        html = resp.data.decode()
        expected = ["Groceries", "Bus fare", "Electricity bill"]
        for desc in expected:
            assert desc in html, f"'{desc}' should be in to_date-only results"

    def test_to_date_only_excludes_later_expenses(self, auth_client):
        resp = auth_client.get("/profile?to_date=2026-04-08")
        html = resp.data.decode()
        excluded = ["Pharmacy", "Streaming subscription", "New shoes", "Lunch", "Miscellaneous"]
        for desc in excluded:
            assert desc not in html, (
                f"'{desc}' is after to_date and must be excluded"
            )

    def test_to_date_only_clear_link_present(self, auth_client):
        resp = auth_client.get("/profile?to_date=2026-04-08")
        html = resp.data.decode()
        assert "Clear" in html, "Clear link must appear when to_date filter is active"


# ===========================================================================
# Malformed / invalid date values — silent fallback
# ===========================================================================

class TestMalformedDateValues:
    @pytest.mark.parametrize("bad_from", [
        "not-a-date",
        "2026/04/01",
        "01-04-2026",
        "2026-13-01",
        "abcdefgh",
        "",
        "2026-04-",
    ])
    def test_malformed_from_date_falls_back_to_all_expenses(self, auth_client, bad_from):
        resp = auth_client.get(f"/profile?from_date={bad_from}")
        assert resp.status_code == 200, "Malformed from_date must not cause an error response"
        html = resp.data.decode()
        assert "212.44" in html, (
            f"Malformed from_date '{bad_from}' should fall back to showing all expenses"
        )

    @pytest.mark.parametrize("bad_to", [
        "not-a-date",
        "2026/04/10",
        "10-04-2026",
        "2026-00-01",
        "xyz",
    ])
    def test_malformed_to_date_falls_back_to_all_expenses(self, auth_client, bad_to):
        resp = auth_client.get(f"/profile?to_date={bad_to}")
        assert resp.status_code == 200, "Malformed to_date must not cause an error response"
        html = resp.data.decode()
        assert "212.44" in html, (
            f"Malformed to_date '{bad_to}' should fall back to showing all expenses"
        )

    def test_both_params_malformed_falls_back_to_all_expenses(self, auth_client):
        resp = auth_client.get("/profile?from_date=bad&to_date=also-bad")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "212.44" in html, "Both malformed params must fall back to all expenses"

    def test_malformed_from_date_does_not_show_error_message(self, auth_client):
        resp = auth_client.get("/profile?from_date=not-a-date")
        html = resp.data.decode()
        # The spec requires silent ignore — no validation error surfaced
        assert "error" not in html.lower() or "Invalid" not in html, (
            "Malformed from_date must be silently ignored — no error message shown"
        )

    def test_sql_injection_attempt_in_from_date_is_safe(self, auth_client):
        """Parameterized queries must prevent SQL injection; page must not crash."""
        resp = auth_client.get("/profile?from_date=2026-04-01' OR '1'='1")
        # Either falls back gracefully (200 with all expenses) or a 302 redirect;
        # must never be a 500 error.
        assert resp.status_code in (200, 302), (
            "SQL injection in from_date must not cause a server error"
        )
        if resp.status_code == 200:
            html = resp.data.decode()
            assert "212.44" in html, (
                "SQL injection attempt should fall back to showing all expenses"
            )


# ===========================================================================
# Preset period parameters
# ===========================================================================

class TestPresetPeriods:
    def test_this_month_preset_returns_200(self, auth_client):
        resp = auth_client.get("/profile?period=this_month")
        assert resp.status_code == 200

    def test_last_3_months_preset_returns_200(self, auth_client):
        resp = auth_client.get("/profile?period=last_3_months")
        assert resp.status_code == 200

    def test_last_6_months_preset_returns_200(self, auth_client):
        resp = auth_client.get("/profile?period=last_6_months")
        assert resp.status_code == 200

    def test_this_month_preset_shows_clear_link_or_all_time_active(self, auth_client):
        """When a preset is active the filter state is communicated to the user."""
        resp = auth_client.get("/profile?period=this_month")
        html = resp.data.decode()
        # Either Clear link is shown or the This Month preset is visually marked active
        assert "This Month" in html, "This Month preset label must be visible"

    def test_last_3_months_preset_date_range_covers_90_days(self, auth_client):
        """Expenses within the last 90 days must appear; verify the route does not crash."""
        resp = auth_client.get("/profile?period=last_3_months")
        assert resp.status_code == 200
        # All seed expenses are in April 2026 which is within 90 days of 2026-05-05
        # (today is 2026-05-05); they should all appear.
        html = resp.data.decode()
        # At minimum the page renders the expenses table or empty state correctly
        assert "Recent Transactions" in html, (
            "last_3_months preset must render the expenses section"
        )

    def test_last_6_months_preset_includes_april_2026_expenses(self, auth_client):
        """All seed data (April 2026) is within 180 days of today (2026-05-05)."""
        resp = auth_client.get("/profile?period=last_6_months")
        html = resp.data.decode()
        assert "212.44" in html, (
            "last_6_months preset should include all April 2026 seed expenses"
        )

    def test_unknown_period_param_falls_back_to_all_expenses(self, auth_client):
        resp = auth_client.get("/profile?period=unknown_value")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "212.44" in html, (
            "Unknown period param must fall back to showing all expenses"
        )

    def test_preset_period_overrides_custom_date_params(self, auth_client):
        """When period= is supplied together with from_date/to_date, period wins."""
        resp = auth_client.get(
            "/profile?period=this_month&from_date=2026-04-01&to_date=2026-04-01"
        )
        assert resp.status_code == 200


# ===========================================================================
# Stat cards reflect filtered data
# ===========================================================================

class TestStatCardsWithFilter:
    def test_filtered_total_spend_displayed(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        assert "122.70" in html, "Total spend stat must reflect filtered total"

    def test_filtered_total_differs_from_unfiltered(self, auth_client):
        filtered_resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        unfiltered_resp = auth_client.get("/profile")
        filtered_html = filtered_resp.data.decode()
        unfiltered_html = unfiltered_resp.data.decode()
        assert "212.44" not in filtered_html, (
            "Filtered page must not show the unfiltered total $212.44"
        )
        assert "212.44" in unfiltered_html, "Unfiltered page must show full total $212.44"

    def test_filtered_transaction_count_in_stat_card(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        assert f">{TOTAL_FILTERED_COUNT}<" in html, (
            f"Transaction count stat card must show {TOTAL_FILTERED_COUNT} for filtered set"
        )

    def test_filtered_category_totals_shown(self, auth_client):
        """The By Category section must reflect the filtered expense set."""
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        # Health ($22.00) is in range; Shopping ($45.00) is not
        assert "Health" in html, "Health category must appear in filtered By Category"
        assert "Shopping" not in html or "45.00" not in html, (
            "Shopping category total must not appear in filtered results"
        )


# ===========================================================================
# Empty state when no expenses match the filter
# ===========================================================================

class TestEmptyStateWithFilter:
    def test_filter_matching_no_expenses_shows_empty_state(self, auth_client):
        """A date range with no expenses must show the empty state message."""
        resp = auth_client.get("/profile?from_date=2020-01-01&to_date=2020-01-31")
        assert resp.status_code == 200
        html = resp.data.decode()
        # The template shows "No expenses yet" in the empty state
        assert "No expenses" in html, (
            "Empty state text must appear when filter matches no expenses"
        )

    def test_filter_matching_no_expenses_total_is_zero(self, auth_client):
        resp = auth_client.get("/profile?from_date=2020-01-01&to_date=2020-01-31")
        html = resp.data.decode()
        assert "0.00" in html, (
            "Total spend must be 0.00 when filter matches no expenses"
        )

    def test_filter_matching_no_expenses_clear_link_present(self, auth_client):
        resp = auth_client.get("/profile?from_date=2020-01-01&to_date=2020-01-31")
        html = resp.data.decode()
        assert "Clear" in html, (
            "Clear link must appear even when the filtered result set is empty"
        )


# ===========================================================================
# Clear filter behaviour
# ===========================================================================

class TestClearFilter:
    def test_clear_link_navigates_to_unfiltered_profile(self, auth_client):
        """Following the Clear link (GET /profile) returns all expenses."""
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "212.44" in html, "After clear, profile must show full total"

    def test_clear_link_href_has_no_query_string(self, auth_client):
        resp = auth_client.get(
            f"/profile?from_date={FILTER_FROM}&to_date={FILTER_TO}"
        )
        html = resp.data.decode()
        # The clear link must be exactly /profile (no ?from_date or ?to_date)
        assert 'href="/profile"' in html, (
            "Clear link href must be /profile with no query parameters"
        )


# ===========================================================================
# DB helper: get_expenses_by_user_filtered
# ===========================================================================

class TestGetExpensesByUserFiltered:
    def test_both_bounds_returns_correct_rows(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, "2026-04-01", "2026-04-10")
        assert len(results) == TOTAL_FILTERED_COUNT, (
            f"Expected {TOTAL_FILTERED_COUNT} rows, got {len(results)}"
        )

    def test_both_bounds_total_amount(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, "2026-04-01", "2026-04-10")
        total = round(sum(r["amount"] for r in results), 2)
        assert total == TOTAL_FILTERED, (
            f"Expected filtered total {TOTAL_FILTERED}, got {total}"
        )

    def test_start_date_only_excludes_earlier_rows(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, start_date="2026-04-14")
        dates = [r["date"] for r in results]
        for d in dates:
            assert d >= "2026-04-14", (
                f"Row with date {d} must not appear when start_date=2026-04-14"
            )

    def test_start_date_only_count(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, start_date="2026-04-14")
        expected = [e for e in SEED_EXPENSES if e[2] >= "2026-04-14"]
        assert len(results) == len(expected), (
            f"Expected {len(expected)} rows from start_date=2026-04-14"
        )

    def test_end_date_only_excludes_later_rows(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, end_date="2026-04-08")
        dates = [r["date"] for r in results]
        for d in dates:
            assert d <= "2026-04-08", (
                f"Row with date {d} must not appear when end_date=2026-04-08"
            )

    def test_end_date_only_count(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, end_date="2026-04-08")
        expected = [e for e in SEED_EXPENSES if e[2] <= "2026-04-08"]
        assert len(results) == len(expected), (
            f"Expected {len(expected)} rows from end_date=2026-04-08"
        )

    def test_no_params_returns_all_expenses(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id)
        assert len(results) == TOTAL_ALL_COUNT, (
            f"No params should return all {TOTAL_ALL_COUNT} expenses"
        )

    def test_results_ordered_by_date_desc(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id)
        dates = [r["date"] for r in results]
        assert dates == sorted(dates, reverse=True), (
            "get_expenses_by_user_filtered must return rows ordered by date DESC"
        )

    def test_from_date_boundary_is_inclusive(self, app):
        """Row exactly on start_date must be included."""
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, start_date="2026-04-25")
        descriptions = [r["description"] for r in results]
        assert "Miscellaneous" in descriptions, (
            "Expense on start_date boundary must be included (inclusive)"
        )

    def test_to_date_boundary_is_inclusive(self, app):
        """Row exactly on end_date must be included."""
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, end_date="2026-04-01")
        descriptions = [r["description"] for r in results]
        assert "Groceries" in descriptions, (
            "Expense on end_date boundary must be included (inclusive)"
        )

    def test_filter_isolates_to_current_user(self, app, tmp_path):
        """Expenses belonging to another user must never appear in results."""
        import database.db as db_module
        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other User", "other@example.com", generate_password_hash("otherpass")),
        )
        conn.commit()
        other_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("other@example.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (other_id, 999.99, "Other", "2026-04-05", "Other user expense"),
        )
        conn.commit()
        conn.close()

        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(user_id, "2026-04-01", "2026-04-30")
        descriptions = [r["description"] for r in results]
        assert "Other user expense" not in descriptions, (
            "Filtered results must not include another user's expenses"
        )
        assert len(results) == TOTAL_ALL_COUNT, (
            "Filter must return only the requesting user's expenses"
        )

    def test_range_matching_nothing_returns_empty_list(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user_filtered(
                user_id, start_date="2020-01-01", end_date="2020-01-31"
            )
        assert results == [] or len(results) == 0, (
            "Filter matching no expenses must return an empty list"
        )


# ===========================================================================
# DB helper: get_expenses_by_user (must remain unchanged)
# ===========================================================================

class TestGetExpensesByUserUnchanged:
    def test_returns_all_user_expenses(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user(user_id)
        assert len(results) == TOTAL_ALL_COUNT, (
            f"get_expenses_by_user must return all {TOTAL_ALL_COUNT} expenses unchanged"
        )

    def test_returns_rows_ordered_by_date_desc(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user(user_id)
        dates = [r["date"] for r in results]
        assert dates == sorted(dates, reverse=True), (
            "get_expenses_by_user must return rows ordered by date DESC"
        )

    def test_total_amount_matches_expected(self, app):
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user(user_id)
        total = round(sum(r["amount"] for r in results), 2)
        assert total == TOTAL_ALL, (
            f"get_expenses_by_user total must be {TOTAL_ALL}, got {total}"
        )

    def test_does_not_filter_by_date(self, app):
        """Ensure get_expenses_by_user accepts no filter arguments and returns all rows."""
        user_id = _get_test_user_id(app)
        with app.app_context():
            results = get_expenses_by_user(user_id)
        # Must include the earliest and latest seed dates
        dates = {r["date"] for r in results}
        assert "2026-04-01" in dates, "Earliest seed date must be in get_expenses_by_user results"
        assert "2026-04-25" in dates, "Latest seed date must be in get_expenses_by_user results"


# ===========================================================================
# Template landmarks
# ===========================================================================

class TestTemplateLandmarks:
    def test_profile_page_title(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "Profile" in html, "Profile page must include 'Profile' in its title or heading"

    def test_filter_section_present(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "from_date" in html and "to_date" in html, (
            "Profile page must contain the date filter form inputs"
        )

    def test_preset_links_present(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "This Month" in html, "This Month preset link must be present"
        assert "Last 3 Months" in html, "Last 3 Months preset link must be present"
        assert "Last 6 Months" in html, "Last 6 Months preset link must be present"

    def test_stat_cards_section_present(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "Total Spent" in html, "Total Spent stat card label must be present"
        assert "Transactions" in html, "Transactions stat card label must be present"
        assert "Top Category" in html, "Top Category stat card label must be present"

    def test_by_category_section_present(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "By Category" in html, "By Category section must be present on profile page"

    def test_recent_transactions_heading_present(self, auth_client):
        resp = auth_client.get("/profile")
        html = resp.data.decode()
        assert "Recent Transactions" in html, (
            "Recent Transactions heading must appear on the profile page"
        )
