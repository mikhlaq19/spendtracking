# Spec: Login and Logout

## Overview
Implement the login and logout flows so existing users can authenticate with their email and password and end their session cleanly. The `GET /login` route and `login.html` template already exist as stubs; this step adds the `POST /login` handler, a `get_user_by_email()` helper in `database/db.py`, server-side credential verification via werkzeug, Flask session management, and a real `GET /logout` route. On success the user is redirected to `/profile`; on failure the form is re-rendered with the email preserved and an inline error. Logout clears the session and redirects to `/`. This unblocks Step 4 (Profile) by establishing the session identity that protected routes will check.

## Depends on
- Step 1 — Database Setup (`get_db()`, `users` table with `email` and `password_hash` columns)
- Step 2 — Registration (real user rows exist to authenticate against)

## Routes
- `POST /login` — accepts email and password; validates presence; looks up user by email; verifies password hash; sets `session['user_id']` on success and redirects to `/profile`; re-renders form with error on failure — public
- `GET /logout` — clears the session; redirects to `/` — public

The existing `GET /login` stub stays; it will share the same view function via `methods=["GET", "POST"]`.

## Database changes
No new tables or columns. One new helper function in `database/db.py`:
- `get_user_by_email(email)` — fetches a single `users` row by email using `LOWER()` for case-insensitive matching; returns the row as `sqlite3.Row` or `None` if not found.

## Templates
- **Create:** none
- **Modify:** `templates/login.html`
  - Replace hardcoded `action="/login"` with `action="{{ url_for('login') }}"`
  - Add `value="{{ email or '' }}"` to the email input so the submitted address is preserved on validation errors
  - Never preserve the password field value

## Files to change
- `app.py`
  - Add `session` to the Flask import line
  - Add `check_password_hash` to the werkzeug import line
  - Set `app.secret_key = "dev-secret-change-in-prod"` immediately after `app = Flask(__name__)`
  - Import `get_user_by_email` from `database.db`
  - Update the `/login` route decorator to `methods=["GET", "POST"]`; on `GET` render the empty form; on `POST` validate, look up, verify, set session, redirect or re-render
  - Replace the `/logout` stub string return with `session.clear()` then `redirect(url_for("landing"))`
- `database/db.py`
  - Add `get_user_by_email(email)` — parameterised `SELECT … WHERE LOWER(email) = LOWER(?)`, returns one row or `None`
- `templates/login.html`
  - Fix hardcoded action URL
  - Add email value preservation

## Files to create
None.

## New dependencies
No new dependencies. Uses `werkzeug.security.check_password_hash` (werkzeug already in requirements.txt) and `flask.session` (built into Flask).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plain text
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only — no `sqlite3` calls or SQL strings in `app.py`
- Use `abort()` for HTTP errors, never bare string returns
- Strip and lowercase the submitted email before the lookup so it matches stored values
- Validation order in the POST handler, with these exact error messages:
  1. Either field blank after stripping → `"Email and password are required."`
  2. No user found for that email, or password hash does not match → `"Invalid email or password."` (same message for both — never hint which field was wrong)
- On success: `session['user_id'] = user['id']`, then `redirect(url_for('profile'))`
- On failure: re-render `login.html` with `error=…` and `email=…` (never `password=…`)
- Logout must use `session.clear()` (not just `session.pop`) and redirect — no template render

## Definition of done
- [ ] Submitting valid credentials sets `session['user_id']` and redirects the browser to `/profile`
- [ ] Submitting an email that does not exist re-renders the login form with `"Invalid email or password."` and keeps the entered email visible in the field
- [ ] Submitting the correct email with the wrong password re-renders with `"Invalid email or password."` (no hint about which field was wrong)
- [ ] Submitting with either field blank re-renders with `"Email and password are required."`
- [ ] The `<form>` action attribute renders as `/login` (via `url_for('login')`) — confirmed by viewing page source
- [ ] Visiting `/logout` clears the session and redirects to `/`
- [ ] `get_user_by_email()` exists in `database/db.py`, uses `?` placeholders, and returns `None` for an unknown email
- [ ] `app.py` contains zero SQL strings and zero `sqlite3` references
- [ ] `app.secret_key` is set so Flask session cookies work without a `RuntimeError`
- [ ] Existing routes (`/`, `/register`, `/terms`, `/privacy`, Step 4+ stubs) still respond as before
