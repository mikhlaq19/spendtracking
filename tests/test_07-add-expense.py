"""
tests/test_07-add-expense.py

Tests for the add-expense feature (Step 7).

Spec: .claude/specs/07-add-expense.md

Covered behaviours
------------------
- Auth guard: GET /expenses/add redirects unauthenticated visitors to /login
- Auth guard: POST /expenses/add redirects unauthenticated visitors to /login
- Happy path GET: logged-in user receives 200 with the add-expense form
- Happy path POST: valid submission redirects to /profile
- DB side effect: valid POST inserts exactly one row with correct field values
- Validation — blank amount: form re-renders with error, no DB insert
- Validation — non-numeric amount: form re-renders with error, no DB insert
- Validation — zero amount: form re-renders with error, no DB insert
- Validation — negative amount: form re-renders with error, no DB insert
- Validation — missing date: form re-renders with error, no DB insert
- Validation — malformed date: form re-renders with error, no DB insert
- Validation — invalid category: form re-renders with error, no DB insert
- Field pre-population: submitted values present in re-rendered form on error
- Description optional: valid POST without description succeeds and stores NULL
"""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import init_db, get_expenses_by_user

# ---------------------------------------------------------------------------
# Allowed categories (mirror of app.py EXPENSE_CATEGORIES — spec-mandated list)
# ---------------------------------------------------------------------------
ALLOWED_CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]

# A known-valid expense payload used in happy-path tests
VALID_PAYLOAD = {
    "amount": "42.50",
    "category": "Food",
    "date": "2026-05-01",
    "description": "Test lunch",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    """
    Isolated Flask application backed by a per-test temporary SQLite file.

    get_db() in database/db.py builds its own connection from DB_PATH, so we
    monkey-patch DB_PATH on the module to point every helper at the temp file.
    The original path is restored after each test so other modules are not
    affected.
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
        # Insert a single test user — no seed data so expense counts are
        # predictable in every test.
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                "Test User",
                "testuser@example.com",
                generate_password_hash("testpass1"),
                "2025-01-15 10:00:00",
            ),
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
    """Test client pre-logged-in as testuser@example.com."""
    resp = client.post(
        "/login",
        data={"email": "testuser@example.com", "password": "testpass1"},
        follow_redirects=False,
    )
    assert resp.status_code == 302, (
        "Login fixture failed — check test user credentials"
    )
    return client


# ---------------------------------------------------------------------------
# Helper: raw DB access inside a test
# ---------------------------------------------------------------------------

def _get_test_user_id(app):
    import database.db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?",
        ("testuser@example.com",),
    ).fetchone()
    conn.close()
    return row["id"]


def _count_expenses(app):
    """Return the total number of rows in the expenses table."""
    import database.db as db_module
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count


# ===========================================================================
# Auth guard
# ===========================================================================

class TestAuthGuard:
    def test_get_add_expense_unauthenticated_redirects_to_login(self, client):
        """GET /expenses/add must redirect an unauthenticated visitor to /login."""
        resp = client.get("/expenses/add", follow_redirects=False)
        assert resp.status_code == 302, (
            "Unauthenticated GET /expenses/add must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated GET /expenses/add must redirect to /login"
        )

    def test_post_add_expense_unauthenticated_redirects_to_login(self, client):
        """POST /expenses/add must redirect an unauthenticated visitor to /login."""
        resp = client.post(
            "/expenses/add",
            data=VALID_PAYLOAD,
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Unauthenticated POST /expenses/add must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated POST /expenses/add must redirect to /login"
        )

    def test_unauthenticated_post_does_not_insert_expense(self, client, app):
        """An unauthenticated POST must not write any row to the DB."""
        before = _count_expenses(app)
        client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        after = _count_expenses(app)
        assert after == before, (
            "Unauthenticated POST must not insert any expenses into the DB"
        )


# ===========================================================================
# Happy path — GET
# ===========================================================================

class TestHappyPathGet:
    def test_get_add_expense_returns_200(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200, (
            "Authenticated GET /expenses/add must return 200"
        )

    def test_get_add_expense_contains_form_tag(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert "<form" in html, "Response must contain a <form> element"

    def test_get_add_expense_form_posts_to_add_expense(self, auth_client):
        """The form action must point to /expenses/add (spec: url_for('add_expense'))."""
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert 'method="POST"' in html or "method='POST'" in html, (
            "Form must use POST method"
        )
        assert "/expenses/add" in html, (
            "Form action must target /expenses/add"
        )

    def test_get_add_expense_has_amount_input(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert 'name="amount"' in html, "Form must include an amount input"

    def test_get_add_expense_has_category_select(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert 'name="category"' in html, "Form must include a category select"

    def test_get_add_expense_category_select_contains_allowed_options(self, auth_client):
        """Each allowed category must be present as an <option> value."""
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        for cat in ALLOWED_CATEGORIES:
            assert cat in html, (
                f"Category option '{cat}' must be present in the form"
            )

    def test_get_add_expense_has_date_input(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert 'name="date"' in html, "Form must include a date input"

    def test_get_add_expense_date_defaults_to_today(self, auth_client):
        """The date field must be pre-populated with today's date (YYYY-MM-DD)."""
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert today in html, (
            f"Date input must default to today ({today})"
        )

    def test_get_add_expense_has_description_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert 'name="description"' in html, (
            "Form must include a description field"
        )

    def test_get_add_expense_has_cancel_link_to_profile(self, auth_client):
        """The Cancel link must point to /profile."""
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        assert 'href="/profile"' in html, (
            "Cancel link must point to /profile"
        )

    def test_get_add_expense_extends_base_template(self, auth_client):
        """The page must extend base.html — check for a nav or common landmark."""
        resp = auth_client.get("/expenses/add")
        html = resp.data.decode()
        # base.html typically renders a <nav> and the Spendly brand name
        assert "Spendly" in html, (
            "Page must extend base.html (expected 'Spendly' brand text)"
        )


# ===========================================================================
# Happy path — POST (valid submission)
# ===========================================================================

class TestHappyPathPost:
    def test_valid_post_redirects_to_profile(self, auth_client):
        """A valid POST must redirect to /profile."""
        resp = auth_client.post(
            "/expenses/add",
            data=VALID_PAYLOAD,
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Valid POST /expenses/add must return 302"
        )
        assert "/profile" in resp.headers["Location"], (
            "Valid POST must redirect to /profile"
        )

    def test_valid_post_inserts_one_row(self, auth_client, app):
        """A valid POST must insert exactly one row into the expenses table."""
        before = _count_expenses(app)
        auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        after = _count_expenses(app)
        assert after == before + 1, (
            f"Valid POST must insert exactly 1 expense row (before={before}, after={after})"
        )

    def test_valid_post_stores_correct_amount(self, auth_client, app):
        auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        user_id = _get_test_user_id(app)
        with app.app_context():
            expenses = get_expenses_by_user(user_id)
        assert len(expenses) == 1, "Expected exactly one expense after valid POST"
        assert expenses[0]["amount"] == float(VALID_PAYLOAD["amount"]), (
            f"Stored amount must be {VALID_PAYLOAD['amount']}"
        )

    def test_valid_post_stores_correct_category(self, auth_client, app):
        auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        user_id = _get_test_user_id(app)
        with app.app_context():
            expenses = get_expenses_by_user(user_id)
        assert expenses[0]["category"] == VALID_PAYLOAD["category"], (
            f"Stored category must be '{VALID_PAYLOAD['category']}'"
        )

    def test_valid_post_stores_correct_date(self, auth_client, app):
        auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        user_id = _get_test_user_id(app)
        with app.app_context():
            expenses = get_expenses_by_user(user_id)
        assert expenses[0]["date"] == VALID_PAYLOAD["date"], (
            f"Stored date must be '{VALID_PAYLOAD['date']}'"
        )

    def test_valid_post_stores_correct_description(self, auth_client, app):
        auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        user_id = _get_test_user_id(app)
        with app.app_context():
            expenses = get_expenses_by_user(user_id)
        assert expenses[0]["description"] == VALID_PAYLOAD["description"], (
            f"Stored description must be '{VALID_PAYLOAD['description']}'"
        )

    def test_valid_post_expense_belongs_to_logged_in_user(self, auth_client, app):
        """The inserted expense must have the correct user_id."""
        auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        user_id = _get_test_user_id(app)
        with app.app_context():
            expenses = get_expenses_by_user(user_id)
        assert len(expenses) == 1, "Expected one expense for the test user"
        assert expenses[0]["user_id"] == user_id, (
            "Inserted expense must belong to the logged-in user"
        )


# ===========================================================================
# Validation — amount
# ===========================================================================

class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount,label", [
        ("",       "blank"),
        ("abc",    "non-numeric string"),
        ("1.2.3",  "multiple decimals"),
        ("$10",    "currency symbol"),
        ("0",      "zero"),
        ("0.00",   "zero as float string"),
        ("-5.00",  "negative"),
        ("-0.01",  "negative near zero"),
    ])
    def test_invalid_amount_returns_200_with_error(
        self, auth_client, app, bad_amount, label
    ):
        """Any invalid amount must re-render the form (200) with an error message."""
        payload = {**VALID_PAYLOAD, "amount": bad_amount}
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"Invalid amount '{label}' must re-render the form (expected 200)"
        )
        html = resp.data.decode()
        # The form must be present (not a redirect to profile)
        assert "<form" in html, (
            f"Invalid amount '{label}' must keep the form visible in the response"
        )

    @pytest.mark.parametrize("bad_amount,label", [
        ("",       "blank"),
        ("abc",    "non-numeric string"),
        ("1.2.3",  "multiple decimals"),
        ("$10",    "currency symbol"),
        ("0",      "zero"),
        ("0.00",   "zero as float string"),
        ("-5.00",  "negative"),
        ("-0.01",  "negative near zero"),
    ])
    def test_invalid_amount_does_not_insert_row(
        self, auth_client, app, bad_amount, label
    ):
        """No expense must be inserted when the amount is invalid."""
        before = _count_expenses(app)
        payload = {**VALID_PAYLOAD, "amount": bad_amount}
        auth_client.post("/expenses/add", data=payload, follow_redirects=False)
        after = _count_expenses(app)
        assert after == before, (
            f"Invalid amount '{label}' must not insert any expense row"
        )

    def test_blank_amount_shows_error_message(self, auth_client):
        """Blank amount must produce a user-visible error string."""
        resp = auth_client.post(
            "/expenses/add",
            data={**VALID_PAYLOAD, "amount": ""},
            follow_redirects=False,
        )
        html = resp.data.decode()
        # The spec requires a clear error message; we check for common keywords
        assert any(
            kw in html.lower()
            for kw in ("error", "invalid", "required", "valid", "must")
        ), "Blank amount must produce a visible error message"

    def test_non_numeric_amount_shows_error_message(self, auth_client):
        resp = auth_client.post(
            "/expenses/add",
            data={**VALID_PAYLOAD, "amount": "not-a-number"},
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert any(
            kw in html.lower()
            for kw in ("error", "invalid", "numeric", "number", "valid", "must")
        ), "Non-numeric amount must produce a visible error message"

    def test_zero_amount_shows_error_message(self, auth_client):
        resp = auth_client.post(
            "/expenses/add",
            data={**VALID_PAYLOAD, "amount": "0"},
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert any(
            kw in html.lower()
            for kw in ("error", "invalid", "greater", "positive", "zero", "must")
        ), "Zero amount must produce a visible error message"

    def test_negative_amount_shows_error_message(self, auth_client):
        resp = auth_client.post(
            "/expenses/add",
            data={**VALID_PAYLOAD, "amount": "-10.00"},
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert any(
            kw in html.lower()
            for kw in ("error", "invalid", "greater", "positive", "negative", "must")
        ), "Negative amount must produce a visible error message"


# ===========================================================================
# Validation — date
# ===========================================================================

class TestDateValidation:
    @pytest.mark.parametrize("bad_date,label", [
        ("",            "blank"),
        ("31/12/2026",  "DD/MM/YYYY format"),
        ("2026/12/31",  "YYYY/MM/DD with slashes"),
        ("12-31-2026",  "MM-DD-YYYY format"),
        ("not-a-date",  "random string"),
        ("2026-13-01",  "month out of range"),
        ("2026-04-31",  "day out of range for April"),
    ])
    def test_invalid_date_returns_200_with_error(
        self, auth_client, app, bad_date, label
    ):
        """Any invalid date must re-render the form (200) with an error."""
        payload = {**VALID_PAYLOAD, "date": bad_date}
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"Invalid date '{label}' must re-render the form (expected 200)"
        )
        html = resp.data.decode()
        assert "<form" in html, (
            f"Invalid date '{label}' must keep the form in the response"
        )

    @pytest.mark.parametrize("bad_date,label", [
        ("",            "blank"),
        ("31/12/2026",  "DD/MM/YYYY format"),
        ("2026/12/31",  "YYYY/MM/DD with slashes"),
        ("12-31-2026",  "MM-DD-YYYY format"),
        ("not-a-date",  "random string"),
        ("2026-13-01",  "month out of range"),
        ("2026-04-31",  "day out of range for April"),
    ])
    def test_invalid_date_does_not_insert_row(
        self, auth_client, app, bad_date, label
    ):
        """No expense must be inserted when the date is invalid."""
        before = _count_expenses(app)
        payload = {**VALID_PAYLOAD, "date": bad_date}
        auth_client.post("/expenses/add", data=payload, follow_redirects=False)
        after = _count_expenses(app)
        assert after == before, (
            f"Invalid date '{label}' must not insert any expense row"
        )

    def test_invalid_date_shows_error_message(self, auth_client):
        resp = auth_client.post(
            "/expenses/add",
            data={**VALID_PAYLOAD, "date": "not-a-date"},
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert any(
            kw in html.lower()
            for kw in ("error", "invalid", "date", "valid", "must")
        ), "Invalid date must produce a visible error message"


# ===========================================================================
# Validation — category
# ===========================================================================

class TestCategoryValidation:
    @pytest.mark.parametrize("bad_category,label", [
        ("",           "blank / unselected"),
        ("Snacks",     "custom value not in list"),
        ("food",       "lowercase variant"),
        ("FOOD",       "uppercase variant"),
        ("  Food",     "leading whitespace"),
        ("Food ",      "trailing whitespace"),
        ("Electronics","not in allowed list"),
        ("'; DROP TABLE expenses; --", "SQL injection attempt"),
    ])
    def test_invalid_category_returns_200_with_error(
        self, auth_client, app, bad_category, label
    ):
        """Any category value outside the allowed list must re-render the form."""
        payload = {**VALID_PAYLOAD, "category": bad_category}
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        assert resp.status_code == 200, (
            f"Invalid category '{label}' must re-render the form (expected 200)"
        )
        html = resp.data.decode()
        assert "<form" in html, (
            f"Invalid category '{label}' must keep the form in the response"
        )

    @pytest.mark.parametrize("bad_category,label", [
        ("",           "blank / unselected"),
        ("Snacks",     "custom value not in list"),
        ("food",       "lowercase variant"),
        ("Electronics","not in allowed list"),
    ])
    def test_invalid_category_does_not_insert_row(
        self, auth_client, app, bad_category, label
    ):
        """No expense must be inserted when the category is not in the allowed list."""
        before = _count_expenses(app)
        payload = {**VALID_PAYLOAD, "category": bad_category}
        auth_client.post("/expenses/add", data=payload, follow_redirects=False)
        after = _count_expenses(app)
        assert after == before, (
            f"Invalid category '{label}' must not insert any expense row"
        )

    def test_invalid_category_shows_error_message(self, auth_client):
        resp = auth_client.post(
            "/expenses/add",
            data={**VALID_PAYLOAD, "category": "NotACategory"},
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert any(
            kw in html.lower()
            for kw in ("error", "invalid", "category", "valid", "select", "must")
        ), "Invalid category must produce a visible error message"

    @pytest.mark.parametrize("valid_category", ALLOWED_CATEGORIES)
    def test_each_allowed_category_is_accepted(
        self, auth_client, app, valid_category
    ):
        """Every category in the allowed list must be accepted and redirect to /profile."""
        payload = {**VALID_PAYLOAD, "category": valid_category}
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            f"Allowed category '{valid_category}' must produce a 302 redirect"
        )
        assert "/profile" in resp.headers["Location"], (
            f"Allowed category '{valid_category}' must redirect to /profile"
        )


# ===========================================================================
# Field pre-population on validation failure
# ===========================================================================

class TestFieldPrepopulation:
    def test_submitted_amount_present_after_invalid_date(self, auth_client):
        """When the date is invalid, the previously entered amount must still appear."""
        payload = {
            "amount": "99.99",
            "category": "Health",
            "date": "bad-date",
            "description": "Pre-pop test",
        }
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert "99.99" in html, (
            "Amount value must be pre-populated in the re-rendered form"
        )

    def test_submitted_description_present_after_invalid_amount(self, auth_client):
        """When the amount is invalid, the description must be pre-populated."""
        payload = {
            "amount": "bad",
            "category": "Shopping",
            "date": "2026-06-01",
            "description": "Should survive validation failure",
        }
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert "Should survive validation failure" in html, (
            "Description must be pre-populated after a validation failure"
        )

    def test_submitted_date_present_after_invalid_category(self, auth_client):
        """When the category is invalid, the submitted date must be pre-populated."""
        payload = {
            "amount": "15.00",
            "category": "InvalidCat",
            "date": "2026-07-04",
            "description": "",
        }
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert "2026-07-04" in html, (
            "Date value must be pre-populated in the re-rendered form after validation failure"
        )

    def test_submitted_category_selected_after_invalid_amount(self, auth_client):
        """When the amount is invalid, the submitted category must appear in the response."""
        payload = {
            "amount": "-1",
            "category": "Transport",
            "date": "2026-08-01",
            "description": "",
        }
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        html = resp.data.decode()
        assert "Transport" in html, (
            "Submitted category must be pre-populated in the re-rendered form"
        )


# ===========================================================================
# Description is optional
# ===========================================================================

class TestDescriptionOptional:
    def test_valid_post_without_description_redirects_to_profile(self, auth_client):
        """A valid POST with an empty description must still succeed."""
        payload = {**VALID_PAYLOAD, "description": ""}
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "Valid POST with empty description must return 302"
        )
        assert "/profile" in resp.headers["Location"], (
            "Valid POST with empty description must redirect to /profile"
        )

    def test_valid_post_without_description_inserts_row(self, auth_client, app):
        """A valid POST without description must insert one expense row."""
        before = _count_expenses(app)
        payload = {**VALID_PAYLOAD, "description": ""}
        auth_client.post("/expenses/add", data=payload, follow_redirects=False)
        after = _count_expenses(app)
        assert after == before + 1, (
            "Valid POST with empty description must insert one expense row"
        )

    def test_valid_post_without_description_stores_null_description(
        self, auth_client, app
    ):
        """The stored description must be NULL (None) when the field is left empty."""
        payload = {**VALID_PAYLOAD, "description": ""}
        auth_client.post("/expenses/add", data=payload, follow_redirects=False)
        user_id = _get_test_user_id(app)
        with app.app_context():
            expenses = get_expenses_by_user(user_id)
        assert len(expenses) == 1, "Expected exactly one expense"
        assert expenses[0]["description"] is None, (
            "Empty description must be stored as NULL in the database"
        )

    def test_omitted_description_field_also_succeeds(self, auth_client, app):
        """Even if the description key is missing from the POST body entirely, the
        submission must succeed — the field is optional."""
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "description"}
        resp = auth_client.post(
            "/expenses/add",
            data=payload,
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            "POST without description key at all must return 302"
        )
        assert "/profile" in resp.headers["Location"], (
            "POST without description key must redirect to /profile"
        )


# ===========================================================================
# Multiple submissions — isolation check
# ===========================================================================

class TestMultipleSubmissions:
    def test_two_valid_posts_insert_two_rows(self, auth_client, app):
        """Each successful submission must insert an independent row."""
        payload_a = {**VALID_PAYLOAD, "amount": "10.00", "description": "First"}
        payload_b = {**VALID_PAYLOAD, "amount": "20.00", "description": "Second"}

        auth_client.post("/expenses/add", data=payload_a, follow_redirects=False)
        auth_client.post("/expenses/add", data=payload_b, follow_redirects=False)

        user_id = _get_test_user_id(app)
        with app.app_context():
            expenses = get_expenses_by_user(user_id)

        assert len(expenses) == 2, (
            "Two valid POSTs must result in exactly two expense rows"
        )
        descriptions = {e["description"] for e in expenses}
        assert "First" in descriptions, "First submission's description must be stored"
        assert "Second" in descriptions, "Second submission's description must be stored"
