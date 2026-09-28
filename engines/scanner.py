"""Scan orchestration: runs every check, streams step events, stores findings."""

import json
import threading
import traceback
from datetime import datetime

from models import Asset, Finding, Scan, ScanEvent, db

from . import checks as checks_mod
from . import extract as extract_mod
from . import torclient

CATEGORY_HINTS = [
    ("market", ("market", "store", "shop", "vendor", "cart", "checkout", "listing")),
    ("forum", ("forum", "board", "discussion", "thread", "community")),
    ("leak", ("leak", "dump", "combo", "breach", "pastebin", "archive")),
    ("blog", ("blog", "news", "press", "blogspot", "journal")),
    ("index", ("wiki", "directory", "index", "search", "hidden")),
]


def classify(text: str) -> str:
    low = (text or "").lower()
    for cat, keys in CATEGORY_HINTS:
        if any(k in low for k in keys):
            return cat
    return "unknown"


def get_or_create_asset(url: str, source: str = "manual", title: str = "") -> Asset:
    asset = Asset.query.filter_by(url=url).first()
    if not asset:
        asset = Asset(url=url, source=source, kind="onion" if ".onion" in url else "clearnet")
        db.session.add(asset)
    if title and not asset.title:
        asset.title = title
    db.session.commit()
    return asset


class ScanRunner:
    def __init__(self, app, scan_id: int):
        self.app = app
        self.scan_id = scan_id
        self._seq = 0

    # ------------------------------------------------------------- events --
    def emit(self, level: str, message: str, check_id: str = ""):
        self._seq += 1
        ev = ScanEvent(scan_id=self.scan_id, seq=self._seq, level=level,
                       check_id=check_id, message=message)
        db.session.add(ev)
        db.session.commit()

    # ---------------------------------------------------------------- run --
    def run(self):
        scan = Scan.query.get(self.scan_id)
        if not scan:
            return
        total = len(checks_mod.CHECKS)
        scan.status = "running"
        scan.checks_total = total
        db.session.commit()

        asset = get_or_create_asset(scan.target, source=scan.started_by or "manual")
        scan.asset_id = asset.id
        db.session.commit()

        self.emit("info", f"target accepted → {scan.target}")
        self.emit("info", f"egress route: {'tor (' + __import__('config').Config.TOR_SOCKS + ')' if scan.route == 'tor' else 'direct / clearnet'}")
        self.emit("info", f"check plan: {total} modules queued")

        session = torclient.build_session(scan.route)
        pending: list = []

        def add_finding(severity, title, detail):
            d = {"severity": severity, "title": title, "detail": detail}
            pending.append(d)
            return d

        ctx = checks_mod.Context(scan.target, scan.route, session, self.emit, add_finding)

        try:
            for i, check in enumerate(checks_mod.CHECKS, start=1):
                pending.clear()
                self.emit("step", f"[{i}/{total}] {check['title']} — {check['desc']}",
                          check_id=check["id"])
                import time

                t0 = time.time()
                try:
                    raw = check["fn"](ctx) or []
                except Exception as exc:
                    self.emit("err", f"module crashed: {type(exc).__name__}: {exc}", check_id=check["id"])
                    traceback.print_exc()
                    raw = []
                ms = int((time.time() - t0) * 1000)

                # add_finding() results and returned results are the same dicts
                seen = set()
                count = 0
                for f in list(dict.fromkeys([json.dumps(x, sort_keys=True, default=str) for x in (raw + pending)])):
                    d = json.loads(f)
                    key = json.dumps([d.get("severity"), d.get("title")], sort_keys=True)
                    if key in seen:
                        continue
                    seen.add(key)
                    db.session.add(
                        Finding(scan_id=scan.id, asset_id=asset.id, check_id=check["id"],
                                severity=d.get("severity", "info"), title=d.get("title", ""),
                                detail=json.dumps(d.get("detail", {}), default=str))
                    )
                    count += 1
                db.session.commit()

                scan.checks_done = i
                scan.findings_total = (scan.findings_total or 0) + count
                db.session.commit()
                self.emit("ok", f"[{i}/{total}] {check['title']} complete in {ms} ms — {count} finding(s)",
                          check_id=check["id"])
                # UI pacing: keep the transcript legible on very fast (local) targets
                time.sleep(0.18)

            self._apply_notes(asset, ctx)
            self._persist_identifiers(asset, scan, ctx)

            # a slow hidden service can time out on the first attempt while a
            # later probe still lands — keep the dossier internally consistent
            if asset.status_code:
                stale = Finding.query.filter_by(scan_id=scan.id, title="Target unreachable").first()
                if stale:
                    stale.severity = "info"
                    stale.title = "First attempt timed out — host answered later"
                    stale.detail = json.dumps({
                        "status_code": asset.status_code,
                        "note": "reachability probe exceeded its window; a subsequent module "
                                "reached the same host and recorded the response",
                    })
                    db.session.commit()
                    self.emit("warn", "reachability timed out but a later probe answered "
                                      f"(HTTP {asset.status_code}) — finding downgraded")
            self._discover_assets(ctx)

            scan.status = "done"
            scan.finished_at = datetime.utcnow()
            db.session.commit()
            self.emit("ok", f"scan complete — {scan.findings_total} findings, "
                            f"{len(ctx.notes.get('found', {}))} identifier classes, "
                            f"{len(ctx.new_onions)} linked services")
        except Exception as exc:
            scan.status = "failed"
            scan.error = traceback.format_exc()
            db.session.commit()
            self.emit("err", f"scan aborted: {exc}")

    def _apply_notes(self, asset, ctx):
        n = ctx.notes
        if n.get("status_code") is not None:
            asset.status_code = n.get("status_code")
        if "alive" in n:
            asset.alive = n.get("alive")
        if n.get("server_banner"):
            asset.server_banner = n["server_banner"][:255]
        if n.get("cert_subject"):
            asset.cert_subject = n["cert_subject"][:255]
        if n.get("cert_org"):
            asset.cert_org = n["cert_org"][:255]
        if n.get("favicon_hash"):
            asset.favicon_hash = n["favicon_hash"]
        if n.get("title"):
            asset.title = n["title"][:255]
            asset.category = classify(n["title"])
        asset.fingerprint = json.dumps(
            {
                "banner": asset.server_banner,
                "favicon": asset.favicon_hash,
                "cert": asset.cert_subject,
            },
            sort_keys=True,
        )
        asset.last_scan = datetime.utcnow()
        db.session.commit()

    def _persist_identifiers(self, asset, scan, ctx):
        found = ctx.notes.get("found") or {}
        if not found:
            return
        # only persist kinds we model (drop the onion self-reference noise)
        found = {k: v for k, v in found.items() if k in
                 ("pgp", "pgp_fingerprint", "btc", "eth", "xmr", "email",
                  "telegram", "discord", "session_id", "onion", "domain")}
        written = extract_mod.upsert(db, __import__("models").Identifier,
                                     __import__("models").Mention, asset, scan, found)
        self.emit("info", f"entity store: {written} new mention(s) written")

    def _discover_assets(self, ctx):
        for onion in sorted(ctx.new_onions or set())[:20]:
            url = f"http://{onion}"
            if not Asset.query.filter_by(url=url).first():
                db.session.add(Asset(url=url, kind="onion", source="discovered", category="unknown"))
                self.emit("ok", f"queued newly discovered service for autonomous collection: {onion}")
        db.session.commit()


def start_scan(app, scan_id: int):
    def _target():
        with app.app_context():
            ScanRunner(app, scan_id).run()

    t = threading.Thread(target=_target, daemon=True, name=f"scan-{scan_id}")
    t.start()
    return t
