import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from engines import stylometry_engine as sty
from models import Actor, CorpusPost, PersonaLink, db

styl_bp = Blueprint("styl", __name__, url_prefix="/style")


@styl_bp.route("/")
def page():
    posts = CorpusPost.query.order_by(CorpusPost.handle, CorpusPost.id).all()
    result = sty.analyse_posts(posts) if posts else None
    diff, pair = None, None
    a = request.args.get("a")
    b = request.args.get("b")
    if result and a and b and a in result["handles"] and b in result["handles"]:
        corpora = {}
        for p in posts:
            corpora.setdefault(p.handle, []).append(p.text)
        pair = (a, b)
        diff = sty.feature_diff("\n".join(corpora[a]), "\n".join(corpora[b]))
    return render_template("stylometry.html", result=result, posts=posts,
                           diff=diff, pair=pair)


@styl_bp.route("/post", methods=["POST"])
def add_post():
    text = (request.form.get("text") or "").strip()
    handle = (request.form.get("handle") or "").strip()
    title = (request.form.get("title") or "").strip()
    if not text or not handle:
        flash("handle and text are required", "err")
        return redirect(url_for("styl.page"))
    db.session.add(CorpusPost(handle=handle, title=title, text=text,
                              source="analyst", word_count=len(text.split())))
    db.session.commit()
    flash(f"corpus entry added for {handle}", "ok")
    return redirect(url_for("styl.page"))


@styl_bp.route("/post/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    p = db.session.get(CorpusPost, post_id)
    if p:
        db.session.delete(p)
        db.session.commit()
        flash("corpus entry removed", "ok")
    return redirect(url_for("styl.page"))


@styl_bp.route("/compare", methods=["POST"])
def compare():
    a = (request.form.get("text_a") or "").strip()
    b = (request.form.get("text_b") or "").strip()
    result = sty.similarity(a, b) if a and b else None
    return render_template("stylometry_compare.html", a=a, b=b, result=result)


@styl_bp.route("/link", methods=["POST"])
def link():
    a = (request.form.get("a") or "").strip()
    b = (request.form.get("b") or "").strip()
    score = float(request.form.get("score") or 0)
    if not a or not b or a == b:
        flash("cannot link a persona to itself", "err")
        return redirect(url_for("styl.page"))
    evidence = json.dumps({
        "method": "stylometry",
        "score": score,
        "source": "function-word + char n-gram + statistical shape (+ research library when present)",
    })
    existing = PersonaLink.query.filter(
        db.or_(
            db.and_(PersonaLink.actor_a == a, PersonaLink.actor_b == b),
            db.and_(PersonaLink.actor_a == b, PersonaLink.actor_b == a),
        )
    ).filter_by(method="stylometry").first()
    if existing:
        existing.confidence = int(round(score * 100))
        existing.evidence = evidence
    else:
        db.session.add(PersonaLink(actor_a=a, actor_b=b, method="stylometry",
                                   confidence=int(round(score * 100)), evidence=evidence))
    for handle in (a, b):
        act = Actor.query.filter(db.func.lower(Actor.handle) == handle.lower()).first()
        if not act:
            act = Actor(handle=handle, category="unknown", status="style-linked",
                        notes="created from stylometric analysis")
            db.session.add(act)
        act.confidence = max(act.confidence, int(round(score * 100)))
        act.status = "style-linked"
    db.session.commit()
    flash(f"persona link recorded: {a} ↔ {b} @ {int(round(score * 100))}%", "ok")
    return redirect(url_for("styl.page", a=a, b=b))
