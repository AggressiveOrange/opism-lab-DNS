#!/usr/bin/env python3
"""Generate the DNS lab stand from students.csv.

Usage:
    python3 gen.py students.csv            # writes ./stand
    python3 gen.py students.csv --out stand --salt opism-2026 --root-delay 80ms --tld-delay 40ms

CSV columns: id,name[,password]
    id        short lowercase label, used as zone name: s01 -> s01.lab
    name      student name, only printed on the variant card
    password  ttyd password; generated if empty

Row order defines IP (10.53.1.<row>) and port (7000+<row>): append new students at the end,
never reorder rows after the stand is deployed.

Existing student zone files are NEVER overwritten (they hold student work), unless --force-zones.
"""
import argparse
import csv
import json
import random
import re
import secrets
import string
import sys
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = Path(__file__).resolve().parent
ALIASES = ["api", "shop", "blog", "docs", "app", "portal", "status", "files", "news", "wiki"]
HOSTS2 = ["beta", "stage", "test", "canary", "edge", "next", "preview", "lab"]
PATH_WORDS = ["catalog", "items", "users", "reports", "archive", "media", "orders", "search"]
QUERY_KEYS = ["page", "sort", "lang", "id", "q", "limit", "from"]
FRAGMENTS = ["top", "results", "section-2", "comments", "summary"]


def variant(sid: str, salt: str) -> dict:
    """Deterministic per-student parameters: same id + salt -> same variant."""
    r = random.Random(f"{salt}:{sid}")
    zone = f"{sid}.lab"
    alias = r.choice(ALIASES)
    host2 = r.choice(HOSTS2)
    p1, p2 = r.sample(PATH_WORDS, 2)
    k1, k2 = r.sample(QUERY_KEYS, 2)
    uris = [
        f"http://www.{zone}/{p1}/{p2}?{k1}={r.randint(1, 99)}&{k2}={r.choice(['asc', 'uk', 'x'])}#{r.choice(FRAGMENTS)}",
        f"http://{alias}.{zone}:80/{p2}/?{k1}=%D0%BA%D0%B8%D1%97%D0%B2",
        f"http://user:pass@{host2}.{zone}/{p1}#{r.choice(FRAGMENTS)}",
        f"https://www.{zone}:{r.choice([8443, 4443, 9443])}/{p1}/../{p2}",
        f"mailto:admin@{zone}?subject={p1}",
    ]
    return {
        "ttl": r.choice([30, 45, 60, 75, 90, 120]),
        "soa_ttl": r.choice([15, 20, 30, 45, 60, 90, 120]),
        "neg_min": r.choice([20, 30, 40, 60, 90]),
        "alias": alias,
        "host2": host2,
        "ttl2": r.choice([20, 25, 35, 40, 50]),
        "mx_pref": r.choice(range(5, 55, 5)),
        "token": "".join(r.choice("0123456789abcdef") for _ in range(8)),
        "nx": f"new-{''.join(r.choice(string.ascii_lowercase) for _ in range(5))}",
        "uris": uris,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", help="roster CSV (instructor mode)")
    ap.add_argument("--student", help="student mode: build a one-student stand for this id, without instructor files")
    ap.add_argument("--out", default="stand")
    ap.add_argument("--salt", default="opism-2026", help="change it per group/semester to get new variants")
    ap.add_argument("--root-delay", default="80ms")
    ap.add_argument("--tld-delay", default="40ms")
    ap.add_argument("--bind-addr", default="0.0.0.0", help="host address for ttyd ports (127.0.0.1 behind a reverse proxy)")
    ap.add_argument("--force-zones", action="store_true", help="overwrite student zone files (destroys student work)")
    args = ap.parse_args()

    out = Path(args.out)
    env = Environment(loader=FileSystemLoader(HERE / "templates"), undefined=StrictUndefined,
                      keep_trailing_newline=True)
    serial_date = time.strftime("%Y%m%d")
    serial_now = int(time.time())

    if bool(args.csv) == bool(args.student):
        sys.exit("give either a roster CSV or --student <id>")
    if args.student:
        rows = [{"id": args.student, "name": "", "password": ""}]
    else:
        with open(args.csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    students = []
    if True:
        for n, row in enumerate(rows, start=1):
            sid = (row.get("id") or "").strip()
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,9}", sid):
                sys.exit(f"row {n}: bad id {sid!r} (lowercase, starts with a letter, max 10 chars)")
            if n > 250:
                sys.exit("more than 250 students: extend the IP plan first")
            pw = (row.get("password") or "").strip() or secrets.token_urlsafe(8)
            s = {"id": sid, "name": (row.get("name") or "").strip(), "password": pw,
                 "ip": f"10.53.1.{n}", "port": 7000 + n}
            s.update(variant(sid, args.salt))
            students.append(s)
    ids = [s["id"] for s in students]
    if len(set(ids)) != len(ids):
        sys.exit("duplicate ids in CSV")

    def write(path: Path, text: str, mode: int = 0o644) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)

    named = env.get_template("named.conf.j2")
    # root
    write(out / "root/named.conf", named.render(comment="root", zone=".", file="/lab/root.zone"))
    write(out / "root/root.zone", env.get_template("root.zone.j2").render(serial=serial_now))
    # TLD lab.
    write(out / "tld/named.conf", named.render(comment="TLD lab.", zone="lab", file="/lab/lab.zone"))
    write(out / "tld/lab.zone", env.get_template("tld.zone.j2").render(serial=serial_now, students=students))
    # resolvers
    hints = (HERE / "templates/root.hints").read_text()
    for name, se in (("resolver-a", False), ("resolver-b", True)):
        write(out / name / "unbound.conf", env.get_template("unbound.conf.j2").render(name=name, serve_expired=se))
        write(out / name / "root.hints", hints)
    # web
    for name in ("web-a", "web-b"):
        write(out / name / "nginx.conf", env.get_template("nginx.conf.j2").render(name=name))
    # students
    skipped = 0
    for s in students:
        d = out / "students" / s["id"]
        write(d / "named.conf", named.render(comment=f"student {s['id']}", zone=f"{s['id']}.lab",
                                             file=f"/lab/zone/{s['id']}.lab.zone"))
        zf = d / "zone" / f"{s['id']}.lab.zone"
        if zf.exists() and not args.force_zones:
            skipped += 1
        else:
            write(zf, env.get_template("student.zone.j2").render(s=s, serial=serial_date))
            write(d / "serial0", f"{serial_date}01\n")
        (d / "zone").chmod(0o755)
        write(out / "cards" / f"{s['id']}.md", env.get_template("card.md.j2").render(s=s))
    # compose + instructor files
    write(out / "compose.yaml", env.get_template("compose.yaml.j2").render(
        students=students, root_delay=args.root_delay, tld_delay=args.tld_delay, bind_addr=args.bind_addr))
    # minimal list for the smoke test (no answers in it)
    (out / "students.json").write_text(json.dumps([{"id": s["id"], "ip": s["ip"]} for s in students]))
    if args.student:
        print(f"student stand for {args.student} in {out}/; card: {out}/cards/{args.student}.md")
        return
    (out / "instructor").mkdir(parents=True, exist_ok=True)
    with open(out / "instructor/credentials.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "port", "login", "password"])
        for s in students:
            w.writerow([s["id"], s["name"], s["port"], s["id"], s["password"]])
    with open(out / "instructor/answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "ttl", "soa_ttl", "soa_minimum", "expected_negative_ttl", "alias", "host2", "ttl2",
                    "mx_pref", "token", "nx_name"])
        for s in students:
            w.writerow([s["id"], s["ttl"], s["soa_ttl"], s["neg_min"], min(s["soa_ttl"], s["neg_min"]),
                        s["alias"], s["host2"], s["ttl2"], s["mx_pref"], s["token"], s["nx"]])
    (out / "instructor/variants.json").write_text(json.dumps(students, ensure_ascii=False, indent=1))
    print(f"generated {len(students)} students in {out}/ (kept {skipped} existing zone files)")


if __name__ == "__main__":
    main()
