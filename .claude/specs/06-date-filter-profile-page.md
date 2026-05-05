# Spec: Date Filter for Profile Page

## Overview
Add a date-range filter to the profile page so users can narrow the expenses table and all summary stats (total spend, expense count, category totals, top category) to a chosen period. The filter is driven by `from_date` and `to_date` query parameters on `GET /profile`. When both params are present and valid, only expenses whose `date` falls within the range (inclusive) are returned and counted. When omitted, the page behaves exactly as before (all expenses). A small filter form above the expenses section lets the user pick dates and submit; a "Clear" link resets to the unfiltered view. No new pages or routes are needed — this is a pure enhancement to the existing `/profile` route and template.

## Depends on
- Step 1 — Database Setup (`get_db()`, `expenses` table with a `date TEXT` column in YYYY-MM-DD format)
- Step 4 — Profile Page Design (`/profile` route, `profile.html`, `get_expenses_by_user()`)

## Routes
No new routes. The existing `GET /profile` route is extended to accept two optional query parameters:
- `from_date` — start of the range, YYYY-MM-DD (inclusive)
- `to_date` — end of the range, YYYY-MM-DD (inclusive)

If either param is missing or malformed the route falls back to returning all expenses (no error shown).

## Database changes
No new tables or columns. One new helper function in `database/db.py`:

- `get_expenses_by_user_filtered(user_id, start_date=None, end_date=None)` — fetches `expenses` rows for the given `user_id` ordered by `date DESC`. When `start_date` is provided, adds `AND date >= ?`; when `end_date` is provided, adds `AND date <= ?`. Both are optional and may be combined. Uses parameterised queries only.

The existing `get_expenses_by_user()` is kept unchanged — it stays the fallback and is used by tests that do not exercise filtering.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter form above the expenses table with two `<input type="date">` fields (`name="from_date"` and `name="to_date"`) and a "Filter" submit button
  - Pre-populate the date inputs with the current `from_date` / `to_date` values so the applied filter is visible after submission
  - Show a "Clear" link (pointing to `url_for('profile')` with no params) only when at least one filter is active
  - All existing sections (profile header, summary cards, expenses table, empty state) remain; their data now reflects the filtered set when a filter is active
  - Show a brief "Showing results for …" label when a filter is applied so the user knows the stats are scoped

## Files to change
- `app.py`
  - In the `/profile` route: read `request.args.get('from_date')` and `request.args.get('to_date')`
  - Validate both with a simple `datetime.strptime(val, "%Y-%m-%d")` try/except; if either is malformed set it to `None`
  - Call `get_expenses_by_user_filtered(user_id, start_date, end_date)` when at least one valid param is present; fall back to `get_expenses_by_user(user_id)` when both are `None`
  - Pass `from_date` and `to_date` through to the template so the form can pre-populate
  - All derived values (`total_spend`, `category_totals`, `top_category`) are computed from the (possibly filtered) `expenses` list — no changes to that logic needed
- `database/db.py`
  - Add `get_expenses_by_user_filtered(user_id, start_date=None, end_date=None)` with conditional `WHERE` clause building using a `params` list

## Files to create
None.

## New dependencies
No new dependencies. Uses `datetime.strptime` from the standard library (already imported in `app.py`).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL; build the filtered query by appending `?` placeholders and a matching `params` list
- Passwords hashed with werkzeug (no change — just don't break existing auth)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py` only — no SQL strings in `app.py`
- Date validation in the route must be silent: a bad value is treated as if it were absent, not surfaced as an error
- `get_expenses_by_user()` must not be modified — it remains the no-filter baseline
- The filter form must use `method="GET"` so the filter state lives in the URL and can be bookmarked or shared
- `from_date` and `to_date` passed to the template must be the validated string values (or empty string `""` when absent) so Jinja2 can safely set them as input `value` attributes

## Definition of done
- [ ] Visiting `/profile` with no query params shows all expenses and the same totals as before this step (Demo User: 8 expenses, £212.44 total)
- [ ] Visiting `/profile?from_date=2026-04-01&to_date=2026-04-10` shows only expenses dated 2026-04-01 through 2026-04-10 (Demo User: Groceries £12.50, Bus fare £3.20, Electricity bill £85.00, Pharmacy £22.00 — total £122.70)
- [ ] The summary cards (total spend, expense count) update to reflect the filtered set
- [ ] Category totals and top category reflect the filtered set
- [ ] The date inputs are pre-populated with the active filter values after submission
- [ ] A "Clear" link appears when a filter is active and removes all filter params when clicked
- [ ] Submitting with only `from_date` set (no `to_date`) filters to all expenses on or after that date
- [ ] Submitting with only `to_date` set (no `from_date`) filters to all expenses on or before that date
- [ ] A malformed date value (e.g. `from_date=not-a-date`) is silently ignored — the page loads with all expenses as if no filter was given
- [ ] `get_expenses_by_user_filtered()` exists in `database/db.py` and uses only `?` placeholders
- [ ] `get_expenses_by_user()` is unchanged and still works
- [ ] `app.py` contains zero SQL strings and zero `sqlite3` references
- [ ] Existing routes (`/`, `/register`, `/login`, `/logout`, `/terms`, `/privacy`) still respond correctly
