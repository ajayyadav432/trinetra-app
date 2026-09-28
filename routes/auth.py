from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

auth_bp = Blueprint("auth", __name__)

CREDENTIALS = {"admin": "admin"}


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("auth.login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = request.form.get("password") or ""
        if CREDENTIALS.get(u) == p:
            session["user"] = u
            flash(f"session opened · operator {u}", "ok")
            return redirect(request.args.get("next") or url_for("dash.home"))
        flash("credentials rejected", "err")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
