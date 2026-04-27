# Spec: Profile Page Design

## Overview
Implement the `/profile` route so authenticated users land on a real dashboard after logging in. The page shows the user's name, email, and account creation date; a summary card with total spend and expense count; and a read-only table of all their expenses. The route is guarded — unauthenticated visitors are redirected to `/login`. The shared navbar in `base.html` is updated to show "My Profile" and "Log out" for logged-in users instead of "Sign in" and "Get started". This is the first protected route in the app and establishes the pattern every future authenticated page will follow.

## Depends on
- Step 1 — Database Setup (`get_db()`, `users` table, `expenses` table)
- Step 2 — Registration (`create_user()`, user rows exist)
- Step 3 — Login and Logout (`session['user_id']` is set on successful login)

## Routes
- `GET /profile` — renders the profile dashboard for the logged-in user; redirects to `/login` if `session['user_id']` is not set — logged-in only

## Database changes
No new tables or columns. Two new helper functions in `database/db.py`:

- `get_user_by_id(user_id)` — fetches one `users` row by primary key; returns `sqlite3.Row` or `None`
- `get_expenses_by_user(user_id)` — fetches all `expenses` rows for the given `user_id`, ordered by `date DESC`; returns a list of `sqlite3.Row`

## Templates
- **Create:** `templates/profile.html` — the profile dashboard page
- **Modify:** `templates/base.html`
  - Update the nav links block to show different links depending on whether the user is logged in
  - Logged-out (no `session.user_id`): show "Sign in" + "Get started" (current behaviour)
  - Logged-in (`session.user_id` is set): show "My Profile" + "Log out"
  - Use `url_for()` for every link — never hardcode URLs

## Files to change
- `app.py`
  - Import `abort` from `flask`
  - Import `get_user_by_id`, `get_expenses_by_user` from `database.db`
  - Replace the `/profile` stub string return with a real implementation:
    - If `session.get('user_id')` is falsy, `redirect(url_for('login'))`
    - Call `get_user_by_id(session['user_id'])` — if it returns `None`, call `abort(404)`
    - Call `get_expenses_by_user(session['user_id'])`
    - Compute `total_spend` (sum of all expense amounts) in Python, not SQL
    - Render `profile.html` passing `user`, `expenses`, and `total_spend`
- `database/db.py`
  - Add `get_user_by_id(user_id)` — parameterised `SELECT * FROM users WHERE id = ?`; returns one row or `None`
  - Add `get_expenses_by_user(user_id)` — parameterised `SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC`; returns a list (empty list if no expenses)
- `templates/base.html`
  - Replace the static nav-links block with a conditional using `{% if session.user_id %}`

## Files to create
- `templates/profile.html` — extends `base.html`; contains the dashboard layout described below
- `static/css/profile.css` — page-specific styles; linked via `{% block head %}` in `profile.html`

## New dependencies
No new dependencies.

## Template structure for `profile.html`
The page has three visible sections inside `{% block content %}`:

1. **Profile header** — user's name (display heading), email, and formatted member-since date (e.g. "Member since April 2026")
2. **Summary card** — two stat tiles side by side: "Total Spent" showing `£{{ "%.2f"|format(total_spend) }}` and "Expenses" showing the count of rows
3. **Expenses table** — a `<table>` with columns: Date, Description, Category, Amount. Each row is one expense. If `expenses` is empty, show a friendly empty-state message ("No expenses yet — add your first one!") instead of a table. No edit or delete links — those come in Steps 8 and 9.

Include a visible "Add Expense" link/button that points to `url_for('add_expense')`. Since that route is still a stub, clicking it will just show the stub string — that is expected and intentional.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with werkzeug (no change needed here — just don't expose `password_hash` in the template)
- Use CSS variables — never hardcode hex values in `profile.css`
- All templates extend `base.html`
- DB logic lives in `database/db.py` only — no SQL strings in `app.py`
- Do not pass `password_hash` to the template — only pass `user`, `expenses`, `total_spend`
- Auth guard uses `redirect(url_for('login'))`, not `abort()` — redirecting unauthenticated users is the correct pattern for protected pages
- `abort(404)` is the correct response when `get_user_by_id` returns `None` for a valid session (data integrity error)
- Compute `total_spend` in Python: `sum(e['amount'] for e in expenses)`, defaulting to `0.0` for an empty list
- The navbar change in `base.html` must use `session.user_id` (Flask makes `session` available in Jinja2 automatically — no extra template variable needed)

## Definition of done
- [ ] Visiting `/profile` while logged in renders `profile.html` with the user's name, email, and member-since date visible
- [ ] The summary card shows the correct total spend and expense count for the logged-in user (verify against seed data: Demo User has 8 expenses totalling £212.44)
- [ ] The expenses table lists all expenses ordered newest-first
- [ ] Visiting `/profile` while not logged in redirects to `/login` (verify by clearing cookies and navigating directly to `/profile`)
- [ ] The navbar shows "My Profile" and "Log out" when logged in, and "Sign in" / "Get started" when logged out — visible on every page since it is in `base.html`
- [ ] `get_user_by_id()` and `get_expenses_by_user()` exist in `database/db.py` and use `?` placeholders
- [ ] `app.py` contains zero SQL strings and zero `sqlite3` references
- [ ] `profile.css` exists and is linked only from `profile.html` (not from `base.html`)
- [ ] No hex colour values appear in `profile.css` — only CSS variable references
- [ ] Existing routes (`/`, `/register`, `/login`, `/logout`, `/terms`, `/privacy`) still respond correctly after the changes
