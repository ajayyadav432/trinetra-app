"""Demo dataset for TRINETRA.

Everything written here is FICTIONAL and tagged with source 'demo-seed' so the
console is never mistaken for a live collection result. Replace it by running
real collection runs against authorised targets.
"""

import json
import random
import string
from datetime import datetime, timedelta

from app import create_app
from models import (Actor, Asset, CorpusPost, Finding, Identifier, Job, Mention,
                    PersonaLink, Scan, ScanEvent, db)

ALPH = "abcdefghijklmnopqrstuvwxyz234567"


def onion(seed: str) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice(ALPH) for _ in range(56)) + ".onion"


Pgp_A = "9F2C 41A8 D3E7 5B60 1C4D  8A11 7E93 B0F5 6C2A 41D8"
Pgp_B = "41D8 6C2A B0F5 7E93 8A11  1C4D 5B60 D3E7 41A8 9F2C"
WALLET_BTC = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
WALLET_BTC2 = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"

SEED_ASSETS = [
    ("obsidian-bay-main", "market", True, "nginx/1.18.0", "Obsidian Bay — Marketplace"),
    ("obsidian-bay-mirror", "market", True, "nginx/1.18.0", "Obsidian Bay (mirror 02)"),
    ("grimfork-forum", "forum", True, "Apache/2.4.41 (Ubuntu)", "GrimFork Discussion Board"),
    ("nightowl-dumps", "leak", True, "nginx/1.19.0", "Nightowl — dump archive"),
    ("quietpost-blog", "blog", False, "", "QuietPost (offline)"),
    ("silk-archivist", "index", True, "cloudflare", "Silk Archivist directory"),
]

SEED_JOB = [
    ("obsidian mirror watch", "market", "tor", 60),
]


def seed():
    app = create_app()
    with app.app_context():
        if Asset.query.count():
            print("database already seeded — delete trinetra.db to re-seed")
            return

        # ---------------------------------------------------------- assets --
        assets = []
        for i, (slug, cat, alive, banner, title) in enumerate(SEED_ASSETS):
            url = "http://" + onion(f"asset-{slug}")
            a = Asset(
                url=url,
                label=slug,
                category=cat,
                kind="onion",
                title=title,
                alive=alive,
                status_code=200 if alive else 503,
                server_banner=banner,
                source="demo-seed",
                notes="fictional demo record — not a real service",
                first_seen=datetime.utcnow() - timedelta(days=30 + i),
                last_scan=datetime.utcnow() - timedelta(days=1, hours=i),
            )
            if i in (0, 1):
                a.cert_subject = "CN=*.obsidianbay.example, O=Obsidian Hosting Ltd"
                a.cert_org = "Obsidian Hosting Ltd"
                a.favicon_hash = "a94a8fe5ccb19ba61c4c0873d391e987be3291032fc8d4e24f7e8f5e1b7c1d02"
            if i == 3:
                a.favicon_hash = "5e1b7c1d02a94a8fe5ccb19ba61c4c0873d391e987be3291032fc8d4e24f7e8f"
            db.session.add(a)
            assets.append(a)
        db.session.commit()

        # ----------------------------------------------------- identifiers --
        ident_defs = [
            ("pgp", Pgp_A, [0, 1, 3]),
            ("pgp", Pgp_B, [2, 5]),
            ("btc", WALLET_BTC, [0, 1]),
            ("btc", WALLET_BTC2, [3]),
            ("email", "obsidian.sup@protonmail.example", [0, 1]),
            ("email", "grimfork.mod@tuta.example", [2]),
            ("telegram", "nightowl_dumps", [3]),
            ("banner", "nginx/1.18.0", [0, 1]),
            ("banner", "nginx/1.19.0", [3]),
            ("onion", assets[1].url.replace("http://", ""), [0, 2]),
            ("onion", assets[0].url.replace("http://", ""), [1, 4]),
        ]
        for kind, value, idxs in ident_defs:
            ident = Identifier(kind=kind, value=value,
                               norm=(value.lower() if kind != "pgp" else value.replace(" ", "").lower()))
            db.session.add(ident)
            db.session.flush()
            for i in idxs:
                db.session.add(Mention(identifier_id=ident.id, asset_id=assets[i].id))
        db.session.commit()

        # ---------------------------------------------------------- actors --
        actors = [
            Actor(handle="ghostwright", aliases="grey_market_g, gw_2024", category="vendor",
                  confidence=87, status="attributed",
                  notes="verbose formal register; PGP key reuse across obsidian surfaces"),
            Actor(handle="grey_market_g", aliases="ghostwright", category="vendor",
                  confidence=87, status="rebrand-suspected",
                  notes="style twin of ghostwright — likely same operator after market exit"),
            Actor(handle="nightowl", aliases="", category="leak-broker",
                  confidence=65, status="under-collection",
                  notes="telegram handle reused on dump archive"),
            Actor(handle="quietquill", aliases="", category="forum-user",
                  confidence=30, status="unattributed", notes="no cross-surface identifier yet"),
            Actor(handle="obsidian_ops", aliases="obsidian.sup", category="market-admin",
                  confidence=90, status="attributed",
                  notes="admin PGP and wallet co-refer with ghostwright listings"),
        ]
        for a in actors:
            db.session.add(a)

        links = [
            PersonaLink(actor_a="ghostwright", actor_b="grey_market_g", method="stylometry",
                        confidence=87,
                        evidence=json.dumps({"score": 0.87, "signals": ["function words", "em-dash habit", "sentence length"]},
                                            indent=2)),
            PersonaLink(actor_a="ghostwright", actor_b="obsidian_ops", method="pgp",
                        confidence=90,
                        evidence=json.dumps({"fingerprint": Pgp_A, "shared_on": "obsidian mirror + main"}, indent=2)),
            PersonaLink(actor_a="nightowl", actor_b="quietquill", method="handle",
                        confidence=35,
                        evidence=json.dumps({"note": "weak overlap — recorded for completeness"}, indent=2)),
        ]
        for l in links:
            db.session.add(l)

        # -------------------------------------------------- stylometry corpus --
        posts = [
            ("ghostwright", "Escrow terms, revised",
             "It has come to my attention that several buyers continue to release funds before "
             "inspection, which rather defeats the purpose of the arrangement we all agreed to. "
             "Allow me to restate the position clearly — the escrow window is seventy-two hours, "
             "not seventy-two minutes, and disputes raised after that window will be considered "
             "frivolous by default. I have operated under this handle for three seasons without a "
             "single unresolved claim, and I would prefer to keep that record intact. If the terms "
             "are unacceptable, there are other vendors; I will not negotiate the clock. "
             "Documentation for every shipment is archived, signed, and available on request."),
            ("ghostwright", "Regarding the forum outage",
             "The interruption last Tuesday was, as far as I can tell, entirely procedural — the "
             "mirror rotated, DNS did not follow, and half the board spent six hours shouting about "
             "a conspiracy that was really just a stale record. I did post a correction, though it "
             "appears to have scrolled away. What concerns me is not the outage itself, but the "
             "number of members who immediately assumed an exit scam. Reputation, once spent, does "
             "not compound; it decays. Those of you who have traded with me know that I answer "
             "questions at length, usually more length than is wanted, and I will continue to do so."),
            ("grey_market_g", "Escrow terms — new handle, same rules",
             "It has come to my attention that several buyers continue to release funds before "
             "inspection, which rather defeats the purpose of the arrangement we all agreed to. "
             "Allow me to restate the position, clearly: the escrow window is seventy-two hours, "
             "not seventy-two minutes, and disputes raised after that window will be treated as "
             "frivolous by default. I have operated under previous handles across three seasons "
             "without a single unresolved claim, and I intend to keep that record intact. If the "
             "terms are unacceptable there are other vendors; I will not negotiate the clock. "
             "Shipping documentation is archived and signed, available on request."),
            ("grey_market_g", "A note on the mirror rotation",
             "The interruption last week was procedural, as far as I can tell — the mirror rotated, "
             "DNS did not follow, and half the board spent six hours shouting about a conspiracy "
             "that was really just a stale record. I posted a correction, though it scrolled away. "
             "What concerns me is not the outage, but the number of members who immediately assumed "
             "an exit scam. Reputation, once spent, does not compound; it decays. Those who have "
             "traded with me know that I answer questions at length — usually more length than is "
             "wanted — and I intend to continue doing exactly that."),
            ("nightowl", "DUMP DROP 04",
             "NEW DROP TONIGHT 03:00 UTC. 4.2GB COMBO LIST, SORTED BY DOMAIN, CSV AND SQL. "
             "SAMPLES POSTED. NO PM BEFORE YOU READ THE FAQ. PRICE IS FIXED, DO NOT ASK FOR "
             "DISCOUNT. IF THE MIRROR IS DOWN USE THE SECOND LINK. I POST, YOU DOWNLOAD, WE ARE "
             "DONE. NO SUPPORT FOR CREDITS THAT DO NOT VALIDATE — TEST THE SAMPLE FIRST."),
            ("nightowl", "MIRROR ROTATED",
             "MIRROR ROTATED AGAIN. OLD LINK IS DEAD, NEW LINK IS IN THE STICKY. IF YOU SAVED THE "
             "OLD ONION THAT IS YOUR PROBLEM. I WILL NOT REPOST INDIVIDUAL LINKS. CHECKSUMS ARE "
             "POSTED WITH EVERY FILE. I AM NOT A HELPDESK."),
            ("quietquill", "is escrow really necessary?",
             "hey! quick question for the veterans here — is escrow actually necessary for small "
             "orders? like, i've done three trades now, all tiny, and i just released instantly "
             "because it felt rude not to?? maybe i'm being naive lol. also does anyone know why "
             "the board keeps logging me out?? it's SO annoying!! sorry for the wall of text, "
             "i'm on mobile and autocorrect is destroying me today :("),
            ("quietquill", "vendorrecommend?",
             "can someone recommend a vendor for the usual stuff?? ideally someone with a PGP "
             "signed profile because i honestly can't verify anything myself lol. last time i "
             "asked here somebody sent me a DM that looked super fishy?? anyway thanks in advance "
             "you folks are always really patient with newbies and i appreciate it!!"),
        ]
        for handle, title, text in posts:
            db.session.add(CorpusPost(handle=handle, title=title, text=text, source="demo-seed",
                                      word_count=len(text.split())))

        # ------------------------------------------------------- schedule --
        target = assets[1].url
        db.session.add(Job(name=SEED_JOB[0][0], target=target, route="tor",
                           interval_minutes=SEED_JOB[0][3], enabled=True))

        # ------------------------------------------ example completed run --
        scan = Scan(target=assets[0].url, route="tor", status="done",
                    checks_total=13, checks_done=13, findings_total=9,
                    started_by="demo-seed",
                    started_at=datetime.utcnow() - timedelta(days=1),
                    finished_at=datetime.utcnow() - timedelta(days=1, minutes=2))
        db.session.add(scan)
        db.session.commit()
        scan.asset_id = assets[0].id
        db.session.commit()

        sample_findings = [
            ("critical", "Sensitive path exposed", "sensitive",
             {"hits": [{"path": "/server-status", "status": 200, "bytes": 4096},
                       {"path": "/.git/config", "status": 200, "bytes": 311}]}),
            ("high", "Certificate tied to clearnet domain(s)", "tls",
             {"sans": ["*.obsidianbay.example", "obsidianbay.example"],
              "clearnet": ["*.obsidianbay.example", "obsidianbay.example"],
              "subject": "CN=*.obsidianbay.example"}),
            ("high", "Page depends on clearnet infrastructure (pivot surface)", "resources",
             {"resources": [{"host": "cdn.obsidianbay.example", "tags": ["script", "img"]}]}),
            ("high", "Identifiers harvested from page", "identifiers",
             {"counts": {"pgp": 1, "btc": 1, "email": 1, "onion": 1}}),
            ("medium", "Server banner disclosed", "headers", {"banner": "nginx/1.18.0"}),
            ("medium", "Directory listing enabled", "dirlist", {"path": "/images/"}),
            ("medium", "HTML comments leak implementation detail", "meta",
             {"comments": ["TODO: rotate mirror after update", "deployed by ops@obsidian"]}),
            ("low", "Missing security headers", "headers",
             {"missing": ["Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options"]}),
            ("info", "Favicon fingerprint captured", "favicon",
             {"sha256": assets[0].favicon_hash, "bytes": 4122}),
        ]
        for sev, title, check, detail in sample_findings:
            db.session.add(Finding(scan_id=scan.id, asset_id=assets[0].id, check_id=check,
                                   severity=sev, title=title, detail=json.dumps(detail, indent=2)))

        steps = [
            ("info", "target accepted → " + assets[0].url),
            ("info", "egress route: tor (socks5h://127.0.0.1:9050)"),
            ("info", "check plan: 13 modules queued"),
            ("step", "[1/13] Service reachability — fetch the target, record status and latency"),
            ("info", "GET " + assets[0].url),
            ("ok", "HTTP 200 in 812 ms, 51240 bytes, 1 redirect(s)"),
            ("ok", "[1/13] Service reachability complete in 829 ms — 1 finding(s)"),
            ("step", "[2/13] Response header audit — security headers, server banner"),
            ("warn", "Strict-Transport-Security: absent"),
            ("warn", "Content-Security-Policy: absent"),
            ("ok", "Server: nginx/1.18.0"),
            ("ok", "[2/13] Response header audit complete in 6 ms — 2 finding(s)"),
            ("step", "[3/13] TLS certificate analysis — subject, issuer, SANs"),
            ("warn", "certificate SANs reference clearnet names — infrastructure pivot"),
            ("ok", "[3/13] TLS certificate analysis complete in 431 ms — 2 finding(s)"),
            ("step", "[4/13] Sensitive path probe — 18 paths, 8 workers"),
            ("warn", "200 /server-status (4096 bytes)"),
            ("warn", "200 /.git/config (311 bytes)"),
            ("ok", "[4/13] Sensitive path probe complete in 3904 ms — 1 finding(s)"),
            ("step", "[12/13] Identifier extraction — PGP, wallets, e-mails, handles"),
            ("ok", "pgp: -----BEGIN PGP PUBLIC KEY BLOCK-----"),
            ("ok", "btc: " + WALLET_BTC),
            ("ok", "email: obsidian.sup@protonmail.example"),
            ("info", "entity store: 4 new mention(s) written"),
            ("ok", "[12/13] Identifier extraction complete in 2 ms — 1 finding(s)"),
            ("ok", "scan complete — 9 findings, 4 identifier classes, 1 linked services"),
        ]
        for i, (level, msg) in enumerate(steps, 1):
            db.session.add(ScanEvent(scan_id=scan.id, seq=i, level=level, message=msg,
                                     ts=scan.started_at + timedelta(seconds=i * 2)))
        db.session.commit()
        print("seeded:", Asset.query.count(), "assets ·", Identifier.query.count(),
              "identifiers ·", Actor.query.count(), "actors ·",
              CorpusPost.query.count(), "posts ·", Scan.query.count(), "scan(s)")


if __name__ == "__main__":
    seed()
