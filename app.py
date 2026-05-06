import sqlite3
from datetime import datetime, date, timedelta

from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import (
    get_db, init_db, seed_db, create_user,
    get_user_by_email, get_user_by_id,
    get_expenses_by_user, get_expenses_by_user_filtered,
    add_expense as db_add_expense,
)

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-prod"

EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


@app.template_filter('fmt_date')
def fmt_date_filter(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (ValueError, TypeError):
        return value

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        return render_template(
            "register.html",
            error="All fields are required.",
            name=name,
            email=email,
        )

    if len(password) < 8:
        return render_template(
            "register.html",
            error="Password must be at least 8 characters.",
            name=name,
            email=email,
        )

    if password != confirm_password:
        return render_template(
            "register.html",
            error="Passwords do not match.",
            name=name,
            email=email,
        )

    try:
        create_user(name, email, generate_password_hash(password))
    except sqlite3.IntegrityError:
        return render_template(
            "register.html",
            error="An account with that email already exists.",
            name=name,
            email=email,
        )

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template(
            "login.html",
            error="Email and password are required.",
            email=email,
        )

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html",
            error="Invalid email or password.",
            email=email,
        )

    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


def _parse_date(val):
    try:
        datetime.strptime(val, "%Y-%m-%d")
        return val
    except (ValueError, TypeError):
        return None


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = get_user_by_id(session["user_id"])
    if user is None:
        abort(404)

    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    period = request.args.get("period", "")

    if period == "this_month":
        from_date = today.replace(day=1).strftime("%Y-%m-%d")
        to_date = today_str
        active_period = "this_month"
    elif period == "last_3_months":
        from_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        to_date = today_str
        active_period = "last_3_months"
    elif period == "last_6_months":
        from_date = (today - timedelta(days=180)).strftime("%Y-%m-%d")
        to_date = today_str
        active_period = "last_6_months"
    else:
        from_date = _parse_date(request.args.get("from_date", ""))
        to_date = _parse_date(request.args.get("to_date", ""))
        active_period = "custom" if (from_date or to_date) else "all"

    if from_date or to_date:
        expenses = get_expenses_by_user_filtered(session["user_id"], from_date, to_date)
    else:
        expenses = get_expenses_by_user(session["user_id"])

    total_spend = sum(e["amount"] for e in expenses) if expenses else 0.0
    member_since = datetime.strptime(user["created_at"][:10], "%Y-%m-%d").strftime("%B %Y")

    cat_totals_map = {}
    for e in expenses:
        cat = e["category"]
        cat_totals_map[cat] = cat_totals_map.get(cat, 0.0) + e["amount"]
    category_totals = sorted(cat_totals_map.items(), key=lambda x: x[1], reverse=True)
    top_category = category_totals[0][0] if category_totals else "—"

    return render_template(
        "profile.html",
        user=user,
        expenses=expenses,
        total_spend=total_spend,
        member_since=member_since,
        category_totals=category_totals,
        top_category=top_category,
        from_date=from_date or "",
        to_date=to_date or "",
        active_period=active_period,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=EXPENSE_CATEGORIES,
            today=date.today().strftime("%Y-%m-%d"),
        )

    amount_str = request.form.get("amount", "").strip()
    category = request.form.get("category", "")
    date_str = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    error = None
    amount = None

    try:
        amount = float(amount_str)
        if amount <= 0:
            error = "Amount must be greater than zero."
    except (ValueError, TypeError):
        error = "Amount must be a valid number."

    if not error and category not in EXPENSE_CATEGORIES:
        error = "Please select a valid category."

    if not error:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            error = "Please enter a valid date."

    if error:
        return render_template(
            "add_expense.html",
            categories=EXPENSE_CATEGORIES,
            error=error,
            amount=amount_str,
            category=category,
            date=date_str,
            description=description,
        )

    db_add_expense(session["user_id"], amount, category, date_str, description or None)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
