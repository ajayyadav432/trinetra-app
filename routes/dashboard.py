from datetime import datetime, timedelta

from flask import Blueprint, render_template

from models import Actor, Asset, CorpusPost, Finding, Identifier, Mention, PersonaLink, Scan, db

dash_bp = Blueprint("dash", __name__)


@dash_bp.route("/")
def home():
    week_ago = datetime.utcnow() - timedelta(days=7)
    reused = [
        i for i in Identifier.query.all()
        if len({m.asset_id for m in i.mentions}) >= 2
    ]
    sev_counts = dict(
        db.session.query(Finding.severity, db.func.count(Finding.id))
        .group_by(Finding.severity).all()
    )
    recent = Scan.query.order_by(Scan.id.desc()).limit(6).all()
    categories = dict(
        db.session.query(Asset.category, db.func.count(Asset.id)).group_by(Asset.category).all()
    )
    pillars = [
        {
            "n": "01",
            "title": "Infrastructure deanonymisation",
            "body": "Misconfiguration, TLS, banner and clearnet-dependency checks on every hidden service.",
            "value": Finding.query.filter(Finding.check_id.in_(
                ["tls", "resources", "sensitive", "headers", "dirlist"])).count(),
            "unit": "infra findings",
            "href": "scans.new",
        },
        {
            "n": "02",
            "title": "Identifier relationship graph",
            "body": "PGP keys, wallets and handles folded into one cross-market linkage graph.",
            "value": len(reused),
            "unit": "reused identifiers",
            "href": "graph.page",
        },
        {
            "n": "03",
            "title": "Stylometric persona linkage",
            "body": "Function-word, punctuation and n-gram profiling to catch rebranded vendors.",
            "value": PersonaLink.query.filter_by(method="stylometry").count(),
            "unit": "style links",
            "href": "styl.page",
        },
    ]
    return render_template(
        "dashboard.html",
        stats={
            "assets": Asset.query.count(),
            "scans": Scan.query.count(),
            "findings": Finding.query.count(),
            "identifiers": Identifier.query.count(),
            "actors": Actor.query.count(),
            "links": PersonaLink.query.count(),
            "shared": len(reused),
            "posts": CorpusPost.query.count(),
            "live": Asset.query.filter_by(alive=True).count(),
            "open": Asset.query.filter(Asset.last_scan >= week_ago).count(),
        },
        sev=sev_counts,
        categories=categories,
        recent=recent,
        reused=reused[:6],
        pillars=pillars,
        top_links=PersonaLink.query.order_by(PersonaLink.confidence.desc()).limit(5).all(),
    )
