import json

from flask import Blueprint, jsonify, render_template

from engines.correlate import build_graph, linkage_rows
from models import PersonaLink

graph_bp = Blueprint("graph", __name__, url_prefix="/graph")


@graph_bp.route("/")
def page():
    g = build_graph()
    counts = {"asset": 0, "identifier": 0, "actor": 0}
    for n in g.get("nodes", []):
        counts[n["type"]] = counts.get(n["type"], 0) + 1
    stats = g.get("stats", {})
    derived = sum(1 for e in g.get("edges", []) if e.get("derived"))
    return render_template(
        "graph.html",
        linkages=linkage_rows(),
        stats=stats,
        counts=counts,
        node_total=len(g.get("nodes", [])),
        edge_total=len(g.get("edges", [])),
        derived=derived,
    )


@graph_bp.route("/api")
def api():
    return jsonify(build_graph())


@graph_bp.route("/links")
def links():
    return jsonify([l.to_dict() for l in PersonaLink.query.order_by(PersonaLink.confidence.desc()).all()])
