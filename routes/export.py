import json

from flask import Blueprint, Response, abort

from engines import exporter
from models import Finding, Scan

export_bp = Blueprint("export", __name__, url_prefix="/export")


def _csv(name, payload):
    return Response(
        payload,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@export_bp.route("/assets.csv")
def assets_csv():
    return _csv("trinetra_assets.csv", exporter.assets_csv())


@export_bp.route("/identifiers.csv")
def identifiers_csv():
    return _csv("trinetra_identifiers.csv", exporter.identifiers_csv())


@export_bp.route("/actors.csv")
def actors_csv():
    return _csv("trinetra_actors.csv", exporter.actors_csv())


@export_bp.route("/links.csv")
def links_csv():
    return _csv("trinetra_persona_links.csv", exporter.links_csv())


@export_bp.route("/intel.json")
def intel_json():
    return Response(exporter.full_json(), mimetype="application/json",
                    headers={"Content-Disposition": 'attachment; filename="trinetra_intel.json"'})


@export_bp.route("/scan/<int:scan_id>.json")
def scan_json(scan_id):
    scan = Scan.query.get_or_404(scan_id)
    findings = [f.to_dict() for f in Finding.query.filter_by(scan_id=scan.id).all()]
    payload = {"scan": scan.to_dict(), "findings": findings}
    return Response(json.dumps(payload, indent=2, default=str), mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="scan_{scan_id}.json"'})


@export_bp.route("/scan/<int:scan_id>.pdf")
def scan_pdf(scan_id):
    scan = Scan.query.get_or_404(scan_id)
    findings = Finding.query.filter_by(scan_id=scan.id).all()
    pdf = exporter.scan_pdf(scan, scan.asset, findings)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="scan_{scan_id}.pdf"'})
