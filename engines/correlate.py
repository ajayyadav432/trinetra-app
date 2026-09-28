"""Pillar 2 — identifier correlation: build the relationship graph + link scores."""

from collections import defaultdict

from models import Actor, Asset, Identifier, Mention, PersonaLink

CONFIDENCE = {
    1: (35, "LOW", "single shared identifier — possible coincidence"),
    2: (65, "MEDIUM", "two shared identifiers — likely same operator"),
    3: (90, "HIGH", "three or more independent identifiers — near-certain attribution"),
}


def confidence_for(count: int):
    return CONFIDENCE[min(count, 3)]


def shared_identifier_pairs(min_shared: int = 1):
    """Asset ↔ asset pairs joined through reused identifiers."""
    ident_assets = defaultdict(set)
    idents = {}
    for m in Mention.query.all():
        ident_assets[m.identifier_id].add(m.asset_id)
        idents[m.identifier_id] = None

    pair_ids = defaultdict(set)
    for ident_id, assets in ident_assets.items():
        if len(assets) < 2:
            continue
        ident = Identifier.query.get(ident_id)
        assets = sorted(assets)
        for i in range(len(assets)):
            for j in range(i + 1, len(assets)):
                pair_ids[(assets[i], assets[j])].add(ident)

    out = []
    for (a, b), ident_set in pair_ids.items():
        if len(ident_set) < min_shared:
            continue
        score, label, rationale = confidence_for(len(ident_set))
        out.append(
            {
                "asset_a": Asset.query.get(a),
                "asset_b": Asset.query.get(b),
                "identifiers": list(ident_set),
                "count": len(ident_set),
                "score": score,
                "label": label,
                "rationale": rationale,
            }
        )
    return sorted(out, key=lambda r: (-r["count"], -r["score"]))


def linkage_rows():
    rows = []
    for pair in shared_identifier_pairs():
        kinds = sorted({i.kind for i in pair["identifiers"]})
        rows.append(
            {
                "a": pair["asset_a"].url,
                "b": pair["asset_b"].url,
                "a_label": pair["asset_a"].label or pair["asset_a"].title or pair["asset_a"].url,
                "b_label": pair["asset_b"].label or pair["asset_b"].title or pair["asset_b"].url,
                "count": pair["count"],
                "kinds": kinds,
                "score": pair["score"],
                "label": pair["label"],
                "rationale": pair["rationale"],
                "identifiers": [
                    {"kind": i.kind, "value": i.value[:70]} for i in pair["identifiers"]
                ],
            }
        )
    return rows


def build_graph():
    nodes, edges = [], []
    seen = set()

    def node(nid, label, ntype, **meta):
        if nid in seen:
            return
        seen.add(nid)
        nodes.append({"id": nid, "label": label, "type": ntype, **meta})

    # assets
    assets = Asset.query.order_by(Asset.id).all()
    for a in assets:
        node(f"a:{a.id}", (a.label or a.title or a.url)[:44], "asset",
             url=a.url, category=a.category, alive=a.alive,
             last_scan=a.last_scan.isoformat() if a.last_scan else None,
             source=a.source)

    # shared identifiers only (they are the bridges)
    mention_counts = defaultdict(set)
    ident_obj = {}
    for m in Mention.query.all():
        mention_counts[m.identifier_id].add(m.asset_id)
    shared = [i for i in Identifier.query.all() if len(mention_counts.get(i.id, ())) >= 2]
    for ident in shared:
        ident_obj[ident.id] = ident
        node(f"i:{ident.id}", ident.display, "identifier", kind=ident.kind, value=ident.value)
        for asset_id in mention_counts[ident.id]:
            edges.append({"source": f"i:{ident.id}", "target": f"a:{asset_id}",
                          "label": ident.kind, "weight": 1})

    # derived asset ↔ asset confidence edges
    for pair in shared_identifier_pairs(min_shared=2):
        edges.append({
            "source": f"a:{pair['asset_a'].id}",
            "target": f"a:{pair['asset_b'].id}",
            "label": f"{pair['label']} · {pair['count']} shared",
            "weight": pair["count"],
            "score": pair["score"],
            "derived": True,
        })

    # actors
    handle_index = {}
    for ident in Identifier.query.filter(Identifier.kind.in_(["email", "telegram", "discord", "onion"])).all():
        handle_index.setdefault(ident.norm, ident.id)

    for actor in Actor.query.all():
        node(f"k:{actor.handle}", actor.handle, "actor", category=actor.category,
             confidence=actor.confidence, status=actor.status, aliases=actor.aliases)
        norm = actor.handle.lower()
        if norm in handle_index:
            ident_id = handle_index[norm]
            ident = Identifier.query.get(ident_id)
            if f"i:{ident_id}" not in seen:
                node(f"i:{ident_id}", ident.display, "identifier", kind=ident.kind, value=ident.value)
                for asset_id in mention_counts.get(ident_id, ()):
                    edges.append({"source": f"i:{ident_id}", "target": f"a:{asset_id}",
                                  "label": ident.kind, "weight": 1})
            edges.append({"source": f"k:{actor.handle}", "target": f"i:{ident_id}",
                          "label": "claimed identifier", "weight": 2})

    # persona linkages
    for link in PersonaLink.query.all():
        for h in (link.actor_a, link.actor_b):
            if f"k:{h}" not in seen:
                node(f"k:{h}", h, "actor", category="unknown", confidence=0, status="unattributed")
        edges.append({
            "source": f"k:{link.actor_a}",
            "target": f"k:{link.actor_b}",
            "label": f"{link.method} · {link.confidence}%",
            "weight": max(1, link.confidence // 25),
            "score": link.confidence,
            "derived": True,
        })

    # legend + stats
    stats = {
        "assets": len(assets),
        "shared_identifiers": len(shared),
        "actors": Actor.query.count(),
        "links": PersonaLink.query.count(),
        "edges": len(edges),
    }
    return {"nodes": nodes, "edges": edges, "stats": stats}
