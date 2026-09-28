"""Exports: CSV / JSON / printable dossier / PDF for the result set."""

import csv
import io
import json
from datetime import datetime

from models import Actor, Asset, Identifier, Mention, PersonaLink


def _iso(dt):
    return dt.isoformat(sep=" ", timespec="seconds") if dt else ""


def assets_csv() -> str:
    buf = io.StringIO()
    fields = ["id", "url", "label", "category", "kind", "alive", "status_code",
              "server_banner", "cert_subject", "cert_org", "favicon_hash",
              "source", "last_scan"]
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for a in Asset.query.order_by(Asset.id).all():
        row = {f: getattr(a, f) for f in fields}
        row["last_scan"] = _iso(a.last_scan)
        row["alive"] = "" if a.alive is None else ("yes" if a.alive else "no")
        w.writerow(row)
    return buf.getvalue()


def identifiers_csv() -> str:
    buf = io.StringIO()
    fields = ["kind", "value", "asset_count", "assets", "first_seen", "last_seen"]
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for ident in Identifier.query.order_by(Identifier.kind, Identifier.value).all():
        assets = [m.asset for m in ident.mentions if m.asset]
        w.writerow({
            "kind": ident.kind,
            "value": ident.value,
            "asset_count": len(assets),
            "assets": " | ".join(a.url for a in assets),
            "first_seen": _iso(ident.first_seen),
            "last_seen": _iso(ident.last_seen),
        })
    return buf.getvalue()


def actors_csv() -> str:
    buf = io.StringIO()
    fields = ["handle", "aliases", "category", "confidence", "status", "last_seen", "notes"]
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for a in Actor.query.order_by(Actor.handle).all():
        w.writerow({
            "handle": a.handle, "aliases": a.aliases, "category": a.category,
            "confidence": a.confidence, "status": a.status,
            "last_seen": _iso(a.last_seen), "notes": a.notes,
        })
    return buf.getvalue()


def links_csv() -> str:
    buf = io.StringIO()
    fields = ["actor_a", "actor_b", "method", "confidence", "evidence", "created_at"]
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    for l in PersonaLink.query.order_by(PersonaLink.confidence.desc()).all():
        w.writerow({"actor_a": l.actor_a, "actor_b": l.actor_b, "method": l.method,
                    "confidence": l.confidence, "evidence": l.evidence,
                    "created_at": _iso(l.created_at)})
    return buf.getvalue()


def full_json() -> str:
    data = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "assets": [a.to_dict() for a in Asset.query.all()],
        "identifiers": [
            {
                "kind": i.kind,
                "value": i.value,
                "first_seen": _iso(i.first_seen),
                "last_seen": _iso(i.last_seen),
                "assets": [m.asset.url for m in i.mentions if m.asset],
            }
            for i in Identifier.query.all()
        ],
        "actors": [a.to_dict() for a in Actor.query.all()],
        "persona_links": [l.to_dict() for l in PersonaLink.query.all()],
    }
    return json.dumps(data, indent=2, default=str)


def scan_pdf(scan, asset, findings) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"TRINETRA scan {scan.id}")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("TRINETRA — Hidden Service Assessment Report", styles["Title"]),
        Paragraph(f"Target: {scan.target}", styles["Normal"]),
        Paragraph(f"Route: {scan.route} &nbsp;|&nbsp; Status: {scan.status} &nbsp;|&nbsp; "
                  f"Started: {_iso(scan.started_at)} &nbsp;|&nbsp; Findings: {len(findings)}",
                  styles["Normal"]),
        Spacer(1, 8),
    ]
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    rows = [["#", "Module", "Severity", "Finding"]]
    for n, f in enumerate(sorted(findings, key=lambda x: sev_order.get(x.severity, 9)), 1):
        rows.append([str(n), f.check_id or "-", (f.severity or "").upper(), f.title])
    table = Table(rows, colWidths=[10 * mm, 30 * mm, 22 * mm, 110 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16150f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#f3efe6")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cfc8b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f4ec"), colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))
    for f in sorted(findings, key=lambda x: sev_order.get(x.severity, 9)):
        story.append(Paragraph(f"<b>[{f.severity.upper()}] {f.title}</b>", styles["Heading4"]))
        detail = f.detail if isinstance(f.detail, str) else json.dumps(f.detail, indent=2)
        story.append(Paragraph(detail.replace("&", "&amp;").replace("<", "&lt;")[:1400],
                               styles["Code"]))
        story.append(Spacer(1, 4))
    doc.build(story)
    return buf.getvalue()
