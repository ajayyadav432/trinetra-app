from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from engines.scanner import start_scan
from models import Job, Scan, db

ops_bp = Blueprint("ops", __name__, url_prefix="/ops")


@ops_bp.route("/")
def page():
    jobs = Job.query.order_by(Job.id).all()
    return render_template("ops.html", jobs=jobs)


@ops_bp.route("/jobs", methods=["POST"])
def add_job():
    name = (request.form.get("name") or "").strip() or "collection pass"
    target = (request.form.get("target") or "").strip()
    if not target:
        flash("target is required", "err")
        return redirect(url_for("ops.page"))
    if "://" not in target:
        target = "http://" + target
    job = Job(
        name=name,
        target=target,
        route=request.form.get("route", "tor"),
        interval_minutes=max(1, int(request.form.get("interval", 30) or 30)),
        enabled=True,
    )
    db.session.add(job)
    db.session.commit()
    flash(f"scheduled '{name}' every {job.interval_minutes} min", "ok")
    return redirect(url_for("ops.page"))


@ops_bp.route("/jobs/<int:job_id>/toggle", methods=["POST"])
def toggle(job_id):
    job = db.session.get(Job, job_id)
    if job:
        job.enabled = not job.enabled
        db.session.commit()
        flash(f"job {'enabled' if job.enabled else 'paused'}", "ok")
    return redirect(url_for("ops.page"))


@ops_bp.route("/jobs/<int:job_id>/run", methods=["POST"])
def run_now(job_id):
    from flask import current_app

    job = db.session.get(Job, job_id)
    if not job:
        return redirect(url_for("ops.page"))
    scan = Scan(target=job.target, route=job.route, status="queued", started_by="scheduler")
    db.session.add(scan)
    job.last_run = datetime.utcnow()
    job.last_status = "dispatched"
    db.session.commit()
    start_scan(current_app._get_current_object(), scan.id)
    flash(f"dispatched manual run of '{job.name}'", "ok")
    return redirect(url_for("ops.page"))


@ops_bp.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete(job_id):
    job = db.session.get(Job, job_id)
    if job:
        db.session.delete(job)
        db.session.commit()
        flash("job removed", "ok")
    return redirect(url_for("ops.page"))
