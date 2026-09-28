from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.utcnow()


class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(512), unique=True, nullable=False, index=True)
    label = db.Column(db.String(160), default="")
    category = db.Column(db.String(40), default="unknown")  # market|forum|leak|blog|index|unknown
    kind = db.Column(db.String(20), default="onion")        # onion|clearnet
    title = db.Column(db.String(255), default="")
    alive = db.Column(db.Boolean, default=None)
    status_code = db.Column(db.Integer, nullable=True)
    server_banner = db.Column(db.String(255), default="")
    cert_subject = db.Column(db.String(255), default="")
    cert_org = db.Column(db.String(255), default="")
    favicon_hash = db.Column(db.String(64), default="")
    fingerprint = db.Column(db.String(255), default="")
    source = db.Column(db.String(60), default="manual")
    notes = db.Column(db.Text, default="")
    first_seen = db.Column(db.DateTime, default=utcnow)
    last_scan = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "label": self.label,
            "category": self.category,
            "kind": self.kind,
            "title": self.title,
            "alive": self.alive,
            "server_banner": self.server_banner,
            "cert_subject": self.cert_subject,
            "cert_org": self.cert_org,
            "favicon_hash": self.favicon_hash,
            "source": self.source,
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
        }


class Scan(db.Model):
    __tablename__ = "scans"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), nullable=True)
    target = db.Column(db.String(512), nullable=False)
    route = db.Column(db.String(12), default="tor")  # tor|direct
    status = db.Column(db.String(20), default="queued")  # queued|running|done|failed
    started_by = db.Column(db.String(60), default="admin")
    checks_total = db.Column(db.Integer, default=0)
    checks_done = db.Column(db.Integer, default=0)
    findings_total = db.Column(db.Integer, default=0)
    error = db.Column(db.Text, default="")
    started_at = db.Column(db.DateTime, default=utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    asset = db.relationship("Asset", backref="scans")

    @property
    def progress(self):
        if not self.checks_total:
            return 0
        return int(100 * self.checks_done / self.checks_total)

    def to_dict(self):
        return {
            "id": self.id,
            "target": self.target,
            "route": self.route,
            "status": self.status,
            "checks_total": self.checks_total,
            "checks_done": self.checks_done,
            "findings_total": self.findings_total,
            "progress": self.progress,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class ScanEvent(db.Model):
    __tablename__ = "scan_events"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scans.id"), index=True)
    seq = db.Column(db.Integer, default=0)
    ts = db.Column(db.DateTime, default=utcnow)
    level = db.Column(db.String(12), default="info")  # info|step|ok|warn|err
    check_id = db.Column(db.String(40), default="")
    message = db.Column(db.Text, default="")

    def to_dict(self):
        return {
            "seq": self.seq,
            "ts": self.ts.strftime("%H:%M:%S"),
            "level": self.level,
            "check_id": self.check_id,
            "message": self.message,
        }


class Finding(db.Model):
    __tablename__ = "findings"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scans.id"), index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), index=True)
    check_id = db.Column(db.String(40))
    severity = db.Column(db.String(12), default="info")  # critical|high|medium|low|info
    title = db.Column(db.String(255))
    detail = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        import json

        try:
            detail = json.loads(self.detail)
        except Exception:
            detail = {}
        return {
            "id": self.id,
            "check_id": self.check_id,
            "severity": self.severity,
            "title": self.title,
            "detail": detail,
        }


class Identifier(db.Model):
    __tablename__ = "identifiers"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), index=True)  # pgp|btc|xmr|eth|email|handle|telegram|onion|domain|banner
    value = db.Column(db.String(512))
    norm = db.Column(db.String(512), index=True)
    first_seen = db.Column(db.DateTime, default=utcnow)
    last_seen = db.Column(db.DateTime, default=utcnow, index=True)
    __table_args__ = (db.UniqueConstraint("kind", "norm", name="uq_ident"),)

    @property
    def display(self):
        if self.kind == "pgp" and len(self.value) > 24:
            return self.value[:24] + "…"
        if len(self.value) > 60:
            return self.value[:60] + "…"
        return self.value


class Mention(db.Model):
    __tablename__ = "mentions"

    id = db.Column(db.Integer, primary_key=True)
    identifier_id = db.Column(db.Integer, db.ForeignKey("identifiers.id"), index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), index=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scans.id"), nullable=True)
    context = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    __table_args__ = (db.UniqueConstraint("identifier_id", "asset_id", name="uq_ment"),)

    identifier = db.relationship("Identifier", backref="mentions")
    asset = db.relationship("Asset", backref="mentions")


class Actor(db.Model):
    __tablename__ = "actors"

    id = db.Column(db.Integer, primary_key=True)
    handle = db.Column(db.String(120), unique=True, nullable=False)
    aliases = db.Column(db.String(255), default="")
    category = db.Column(db.String(40), default="unknown")
    confidence = db.Column(db.Integer, default=0)   # 0-100 attribution confidence
    status = db.Column(db.String(30), default="unattributed")
    first_seen = db.Column(db.DateTime, default=utcnow)
    last_seen = db.Column(db.DateTime, default=utcnow)
    notes = db.Column(db.Text, default="")

    def to_dict(self):
        return {
            "id": self.id,
            "handle": self.handle,
            "aliases": self.aliases,
            "category": self.category,
            "confidence": self.confidence,
            "status": self.status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class PersonaLink(db.Model):
    __tablename__ = "persona_links"

    id = db.Column(db.Integer, primary_key=True)
    actor_a = db.Column(db.String(120), index=True)
    actor_b = db.Column(db.String(120), index=True)
    method = db.Column(db.String(30))   # pgp|wallet|handle|stylometry|infra
    confidence = db.Column(db.Integer, default=0)
    evidence = db.Column(db.Text, default="[]")
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        import json

        try:
            evidence = json.loads(self.evidence)
        except Exception:
            evidence = []
        return {
            "actor_a": self.actor_a,
            "actor_b": self.actor_b,
            "method": self.method,
            "confidence": self.confidence,
            "evidence": evidence,
        }


class CorpusPost(db.Model):
    __tablename__ = "corpus_posts"

    id = db.Column(db.Integer, primary_key=True)
    handle = db.Column(db.String(120), index=True)
    title = db.Column(db.String(255), default="")
    text = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(120), default="manual")
    word_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    target = db.Column(db.String(512), nullable=False)
    route = db.Column(db.String(12), default="tor")
    interval_minutes = db.Column(db.Integer, default=30)
    enabled = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(20), default="")
    created_at = db.Column(db.DateTime, default=utcnow)
