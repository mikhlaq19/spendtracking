# Spec: Registration

## Overview
Implement the user registration flow so new accounts can be created. The `GET /register` route and `register.html` template already exist; this step adds the `POST /register` handler, a `create_user()` helper in `database/db.py`, server-side validation, and inline error feedback. On success the user is redirected to the login page; on failure the form is re-rendered with the user's input preserved and an inline error message. This unblocks Step 3 (Login/Logout) by ensuring real users exist in the database.

## Depends on
- Step 1 — Database Setup (`get_db()`, `init_db()`, `users` table with UNIQUE email constraint)

## Routes
- `POST /register` — accepts name, email, and password from the form; validates them; hashes the password; inserts the user; redirects to `/login` on success — public

The existing `GET /register` route stays as-is; it will share the same view function via `methods=["GET", "POST"]`.

## Database changes
No database changes. The `users` table created in Step 1 already has every column registration needs (`name`, `email` UNIQUE, `password_hash`, `created_at`).

## Templates
- **Create:** none
- **Modify:** `templates/register.html`
  - Replace hardcoded `action="/register"` with `action="{{ url_for('register') }}"` (CLAUDE.md rule)
  - Preserve submitted `name` and `email` on validation errors via `value="{{ name or '' }}"` and `value="{{ email or '' }}"` so the user does not have to retype them. Never preserve the password.
  - The existing `{% if error %}` block is reused for all error messages — no structural changes needed

## Files to change
- `app.py`
  - Import `request`, `redirect`, `url_for` from `flask`
  - Import `create_user` from `database.db`
  - Update the `/register` route decorator to `methods=["GET", "POST"]`
  - On `GET`: render the empty form (current behavior)
  - On `POST`: validate input, call `create_user()`, handle `sqlite3.IntegrityError` for duplicate emails, redirect to `url_for('login')` on success, re-render with `error` and preserved fields on failure
- `database/db.py`
  - Add `create_user(name, email, password_hash)` — runs a parameterised `INSERT` into `users` and returns the new row id. Lets `sqlite3.IntegrityError` propagate so the caller can detect duplicate email
- `templates/register.html`
  - Fix hardcoded action URL
  - Preserve `name` and `email` values on re-render

## Files to create
None.

## New dependencies
No new dependencies. Uses `werkzeug.security.generate_password_hash` (already imported in `database/db.py`) and `sqlite3.IntegrityError` (standard library).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` before being passed to `create_user()`. The route is responsible for hashing; `create_user()` only stores the hash it receives
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only — no `sqlite3` calls or SQL strings inside `app.py`
- Use `abort()` for HTTP errors, never bare string returns
- Strip whitespace from `name` and `email` before validating; lowercase the email before storing so duplicates are caught case-insensitively
- Validation order in the route, with these exact error messages:
  1. Any field empty after stripping → `"All fields are required."`
  2. Password shorter than 8 characters → `"Password must be at least 8 characters."`
  3. `sqlite3.IntegrityError` from `create_user()` → `"An account with that email already exists."`
- On success, return `redirect(url_for('login'))` — do not render a template
- On failure, re-render `register.html` with `error=...`, `name=...`, `email=...` (never `password=...`)
- The route function stays single-responsibility: parse → validate → hash → create → redirect or re-render

## Definition of done
- [ ] Submitting the form with a new name, valid email, and password ≥ 8 characters creates a row in `users` with a hashed password (verified via `sqlite3` CLI or repl) and redirects the browser to `/login`
- [ ] Submitting with an email that already exists re-renders the form with the message `"An account with that email already exists."` and keeps the entered name/email visible
- [ ] Submitting the form with any blank field re-renders with `"All fields are required."`
- [ ] Submitting with a password under 8 characters re-renders with `"Password must be at least 8 characters."`
- [ ] The `<form>` action attribute renders as `/register` (via `url_for('register')`) — confirmed by viewing page source
- [ ] `create_user()` exists in `database/db.py`, uses `?` placeholders, and returns the new user id
- [ ] `app.py` contains zero SQL strings and zero `sqlite3` references
- [ ] Existing routes (`/`, `/login`, `/terms`, `/privacy`, the Step 3+ stubs) still respond as before
- [ ] After registering, the demo user from `seed_db()` and the new user both exist (no overwrite or duplication)
