import json

from flask import Blueprint, abort, render_template, request

from engines.correlate import linkage_rows
from models import Actor, Asset, Identifier, Mention, PersonaLink, Scan, db

intel_bp = Blueprint("intel", __name__, url_prefix="/intel")


@intel_bp.route("/")
def index():
    q = (request.args.get("q") or "").strip().lower()
    kind = request.args.get("kind", "")
    category = request.args.get("category", "")

    assets = Asset.query.order_by(Asset.last_scan.desc().nullslast(), Asset.id.desc())
    if q:
        like = f"%{q}%"
        assets = assets.filter(db.or_(Asset.url.like(like), Asset.title.like(like),
                                      Asset.label.like(like), Asset.server_banner.like(like)))
    if category:
        assets = assets.filter_by(category=category)
    assets = assets.limit(200).all()

    idents = Identifier.query.order_by(Identifier.last_seen.desc())
    if kind:
        idents = idents.filter_by(kind=kind)
    else:
        idents = idents.limit(300)
    ident_rows = []
    for i in idents:
        assets_for = [m.asset for m in i.mentions if m.asset]
        shared = len({a.id for a in assets_for}) >= 2
        ident_rows.append((i, assets_for, shared))

    actors = Actor.query.order_by(Actor.confidence.desc(), Actor.handle).all()
    links = linkage_rows()

    kinds = [k for (k,) in db.session.query(Identifier.kind).distinct().order_by(Identifier.kind)]
    categories = [c for (c,) in db.session.query(Asset.category).distinct().order_by(Asset.category)]

    return render_template(
        "intel.html",
        assets=assets,
        ident_rows=ident_rows,
        actors=actors,
        persona_links=PersonaLink.query.order_by(PersonaLink.confidence.desc()).all(),
        linkages=links,
        kinds=kinds,
        categories=categories,
        filters={"q": q, "kind": kind, "category": category},
    )


@intel_bp.route("/asset/<int:asset_id>")
def asset(asset_id):
    a = Asset.query.get_or_404(asset_id)
    mentions = Mention.query.filter_by(asset_id=a.id).all()
    scans = Scan.query.filter_by(asset_id=a.id).order_by(Scan.id.desc()).all()
    ident_rows = []
    for m in mentions:
        others = [x for x in m.identifier.mentions if x.asset_id != a.id]
        ident_rows.append((m.identifier, [o.asset for o in others if o.asset]))
    return render_template("asset.html", asset=a, ident_rows=ident_rows, scans=scans)


@intel_bp.route("/actor/<path:handle>")
def actor(handle):
    a = Actor.query.filter_by(handle=handle).first_or_404()
    links = [l for l in PersonaLink.query.all() if handle in (l.actor_a, l.actor_b)]
    return render_template("actor.html", actor=a, links=links)
