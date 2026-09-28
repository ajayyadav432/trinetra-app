import json
import time

from flask import (Blueprint, Response, abort, jsonify, redirect, render_template,
                   request, url_for)

from engines.checks import CHECKS
from engines.scanner import start_scan
from models import Finding, Scan, ScanEvent, db

scans_bp = Blueprint("scans", __name__, url_prefix="/scans")


@scans_bp.route("/")
def index():
    rows = Scan.query.order_by(Scan.id.desc()).limit(60).all()
    return render_template("scans.html", scans=rows)


@scans_bp.route("/new")
def new():
    return render_template("scan_new.html", checks=CHECKS,
                           route=request.args.get("route", "tor"))


@scans_bp.route("/start", methods=["POST"])
def start():
    target = (request.form.get("target") or "").strip()
    route = request.form.get("route", "tor")
    if not target:
        return redirect(url_for("scans.new"))
    if "://" not in target:
        target = "http://" + target
    scan = Scan(target=target, route=route if route in ("tor", "direct") else "tor",
                status="queued", started_by="manual")
    db.session.add(scan)
    db.session.commit()
    start_scan(_current_app(), scan.id)
    return redirect(url_for("scans.live", scan_id=scan.id))


def _current_app():
    from flask import current_app

    return current_app._get_current_object()


@scans_bp.route("/<int:scan_id>/live")
def live(scan_id):
    scan = Scan.query.get_or_404(scan_id)
    return render_template("scan_live.html", scan=scan, checks=CHECKS)


@scans_bp.route("/<int:scan_id>")
def detail(scan_id):
    scan = Scan.query.get_or_404(scan_id)
    findings = Finding.query.filter_by(scan_id=scan.id).all()
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: order.get(f.severity, 9))
    enriched = []
    for f in findings:
        try:
            detail_data = json.loads(f.detail)
        except Exception:
            detail_data = {}
        enriched.append((f, detail_data))
    events = ScanEvent.query.filter_by(scan_id=scan.id).order_by(ScanEvent.seq).all()
    return render_template("scan_detail.html", scan=scan, findings=enriched,
                           events=events, checks=CHECKS)


@scans_bp.route("/<int:scan_id>/events")
def events(scan_id):
    Scan.query.get_or_404(scan_id)
    app = _current_app()
    start_after = int(request.args.get("after", 0))

    def generate():
        # streaming responses run after the request context is popped,
        # so re-enter an application context for DB access
        with app.app_context():
            last = start_after
            yield ": connected\n\n"
            while True:
                rows = (ScanEvent.query
                        .filter(ScanEvent.scan_id == scan_id, ScanEvent.seq > last)
                        .order_by(ScanEvent.seq)
                        .limit(60).all())
                for r in rows:
                    last = r.seq
                    yield f"data: {json.dumps(r.to_dict())}\n\n"
                # the scanner thread commits in its own session; drop our
                # identity-mapped copy so status/progress are always fresh
                db.session.expire_all()
                scan = db.session.get(Scan, scan_id)
                status_payload = json.dumps({
                    "status": scan.status,
                    "progress": scan.progress,
                    "checks_done": scan.checks_done,
                    "checks_total": scan.checks_total,
                    "findings": scan.findings_total,
                })
                yield f"data: {status_payload}\n\n"
                if scan.status in ("done", "failed") and not rows:
                    items = Finding.query.filter_by(scan_id=scan_id).order_by(Finding.id).all()
                    done_payload = {
                        "done": True,
                        "status": scan.status,
                        "findings": [f.to_dict() for f in items],
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    break
                time.sleep(0.35)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@scans_bp.route("/api/<int:scan_id>")
def api(scan_id):
    scan = db.session.get(Scan, scan_id)
    if not scan:
        abort(404)
    return jsonify(scan.to_dict())
