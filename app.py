"""TRINETRA — application factory, auth guard, autonomous scheduler."""

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, g, redirect, render_template, request, session, url_for

from config import Config
from models import Job, Scan, db


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    db.init_app(app)

    from routes.auth import auth_bp
    from routes.dashboard import dash_bp
    from routes.export import export_bp
    from routes.graph import graph_bp
    from routes.intel import intel_bp
    from routes.ops import ops_bp
    from routes.scans import scans_bp
    from routes.stylometry import styl_bp

    for bp in (auth_bp, dash_bp, scans_bp, intel_bp, graph_bp, styl_bp, ops_bp, export_bp):
        app.register_blueprint(bp)

    @app.before_request
    def _guard():
        g.user = session.get("user")
        if request.endpoint and not request.endpoint.startswith("auth.") \
                and request.endpoint != "static" and not g.user:
            if request.endpoint.startswith(("scans.stream",)):
                return
            return redirect(url_for("auth.login", next=request.path))

    @app.context_processor
    def _ctx():
        return {"now": datetime.utcnow, "user": getattr(g, "user", None),
                "enumerate": enumerate}

    with app.app_context():
        db.create_all()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(lambda: _tick(app), "interval", seconds=20, id="trinetra-tick")
    app.scheduler = scheduler
    try:
        scheduler.start()
        _sync_jobs(app)
    except Exception:
        pass
    return app


# --------------------------------------------------------------- scheduler --

def _sync_jobs(app):
    """Reconcile interval jobs in the DB with the running scheduler."""
    from engines.scanner import start_scan

    sched = getattr(app, "scheduler", None)
    if not sched:
        return
    with app.app_context():
        jobs = Job.query.filter_by(enabled=True).all()
        wanted = {f"job-{j.id}" for j in jobs}
        for existing in [j for j in sched.get_jobs() if j.id.startswith("job-")]:
            if existing.id not in wanted:
                existing.remove()
        for j in jobs:
            jid = f"job-{j.id}"
            if sched.get_job(jid):
                continue

            def make(job):
                def _run():
                    with app.app_context():
                        scan = Scan(target=job.target, route=job.route,
                                    status="queued", started_by="scheduler")
                        db.session.add(scan)
                        db.session.commit()
                        job.last_run = datetime.utcnow()
                        job.last_status = "dispatched"
                        db.session.commit()
                        start_scan(app, scan.id)

                return _run

            sched.add_job(make(j), "interval", minutes=max(1, j.interval_minutes),
                          id=jid, replace_existing=True)


_last_sync = {"t": None}


def _tick(app):
    """20-second heartbeat: re-sync job registry, advance queued scans."""
    now = datetime.utcnow()
    if _last_sync["t"] is None or (now - _last_sync["t"]).total_seconds() > 60:
        _last_sync["t"] = now
        try:
            _sync_jobs(app)
        except Exception:
            pass
    with app.app_context():
        from engines.scanner import start_scan

        queued = Scan.query.filter_by(status="queued").limit(3).all()
        for scan in queued:
            scan.status = "starting"
            db.session.commit()
            start_scan(app, scan.id)


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False, threaded=True)
