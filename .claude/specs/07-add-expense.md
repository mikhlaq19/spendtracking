# Spec: Add Expense

## Overview
Implement the add-expense feature so logged-in users can record a new expense via a form at `GET /expenses/add`. The form collects amount, category, date, and an optional description. On valid `POST /expenses/add` the expense is saved to the `expenses` table and the user is redirected to their profile page. This is the first write-path feature in Spendly — the stub route at `GET /expenses/add` is replaced with a fully working form and handler.

## Depends on
- Step 1 — Database Setup (`get_db()`, `expenses` table schema with user_id, amount, category, date, description)
- Step 3 — Login / Logout (session-based auth, `session["user_id"]`)
- Step 4 — Profile Page Design (`/profile` route exists for post-submit redirect)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the expense, redirect to `/profile` on success — logged-in only

## Database changes
No new tables or columns. One new helper function in `database/db.py`:

- `add_expense(user_id, amount, category, date, description)` — inserts one row into the `expenses` table. `description` may be `None`. Uses parameterised queries only. Returns the new row's `lastrowid`.

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - Form with `method="POST"` and `action="{{ url_for('add_expense') }}"`
  - Fields: amount (number input, step 0.01, min 0.01), category (select with fixed options), date (date input, defaults to today), description (textarea, optional)
  - Show inline error messages when the form is re-rendered after failed validation
  - Pre-populate field values from the previous submission so the user does not have to retype everything
  - A "Cancel" link pointing to `url_for('profile')`
- **Modify:** none

## Files to change
- `app.py`
  - Replace the `GET /expenses/add` stub with a full route function that:
    - Redirects to `/login` if `session["user_id"]` is absent
    - On `GET`: renders `add_expense.html` with today's date pre-set
    - On `POST`: reads and validates `amount`, `category`, `date`; re-renders the form with an error on failure; calls `add_expense()` and redirects to `url_for('profile')` on success
    - Change route decorator from `GET`-only to `methods=["GET", "POST"]`
  - Import `add_expense` from `database.db`
- `database/db.py`
  - Add `add_expense(user_id, amount, category, date, description)` function

## Files to create
- `templates/add_expense.html` — the add-expense form template
- `static/css/add_expense.css` — page-specific styles (no inline `<style>` tags)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with werkzeug (no change — do not break existing auth)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only — no SQL strings in `app.py`
- Redirect unauthenticated requests with `redirect(url_for('login'))` — do not use `abort()`
- `amount` must be validated as a positive float (`> 0`); reject non-numeric or zero/negative values with a form error
- `category` must be one of the allowed values: Food, Transport, Bills, Health, Entertainment, Shopping, Other — reject any value not in this list
- `date` must be a valid YYYY-MM-DD string; validate with `datetime.strptime(val, "%Y-%m-%d")`; reject malformed dates with a form error
- On validation failure, re-render the form with the submitted values pre-populated and a clear error message — do not redirect
- The allowed category list must be defined once in `app.py` and passed to the template as a context variable — do not hardcode it in the template

## Definition of done
- [ ] `GET /expenses/add` renders the add-expense form for a logged-in user
- [ ] `GET /expenses/add` redirects to `/login` for an unauthenticated visitor
- [ ] Submitting the form with all valid fields inserts one row into `expenses` and redirects to `/profile`
- [ ] The new expense appears in the expenses table on `/profile` after a successful add
- [ ] Submitting with a missing or blank amount shows a form error and does not insert a row
- [ ] Submitting with a non-positive amount (0 or negative) shows a form error and does not insert a row
- [ ] Submitting with a non-numeric amount shows a form error and does not insert a row
- [ ] Submitting with a missing or invalid date shows a form error and does not insert a row
- [ ] Submitting with an invalid category shows a form error and does not insert a row
- [ ] On validation failure the form re-renders with the previously entered values pre-populated
- [ ] `add_expense()` exists in `database/db.py` and uses only `?` placeholders
- [ ] `app.py` contains zero SQL strings and zero `sqlite3` references
- [ ] `static/css/add_expense.css` is linked from `add_expense.html` — no inline `<style>` tags
- [ ] Existing routes (`/`, `/register`, `/login`, `/logout`, `/profile`, `/terms`, `/privacy`) still respond correctly
