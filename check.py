#!/usr/bin/env python3
"""Check student zones against their variants, and smoke-test the stand.

Run on the stand host, next to the generated directory:
    python3 check.py --stand stand --smoke          # after deploy: delegation + resolvers work for every student
    python3 check.py --stand stand                  # grading: records from the variant card
    python3 check.py --stand stand --only s01,s02

By default dig runs inside the root container (docker compose exec), so nothing is needed on the host.
Override with --dig "dig" if the host itself can reach 10.53.0.0/16.
"""
import argparse
import csv
import json
import shlex
import subprocess
import sys
from pathlib import Path


def make_dig(prefix: str):
    def dig(server: str, name: str, rtype: str, recurse: bool = False) -> list[list[str]]:
        cmd = shlex.split(prefix) + [f"@{server}", name, rtype, "+noall", "+answer", "+time=2", "+tries=1"]
        if not recurse:
            cmd.append("+norec")
        p = subprocess.run(cmd, capture_output=True, text=True)
        return [line.split(None, 4) for line in p.stdout.splitlines() if line and not line.startswith(";")]
    return dig


def rdata(rows, rtype):
    return [r[4] for r in rows if len(r) == 5 and r[3] == rtype]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stand", default="stand")
    ap.add_argument("--dig", default=None, help='dig command prefix (default: docker compose exec into root)')
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    stand = Path(args.stand)
    vfile = stand / "instructor/variants.json"
    if args.smoke and not vfile.exists():
        vfile = stand / "students.json"   # student stand: ids and addresses only
    students = json.loads(vfile.read_text())
    if args.only:
        keep = set(args.only.split(","))
        students = [s for s in students if s["id"] in keep]
    prefix = args.dig or f"docker compose -f {stand / 'compose.yaml'} exec -T root dig"
    dig = make_dig(prefix)

    if args.smoke:
        bad = 0
        for s in students:
            z = f"{s['id']}.lab"
            res = {
                "auth": rdata(dig(s["ip"], z, "SOA"), "SOA"),
                "resolver-a": rdata(dig("10.53.0.53", f"ns.{z}", "A", recurse=True), "A"),
                "resolver-b": rdata(dig("10.53.0.54", f"ns.{z}", "A", recurse=True), "A"),
            }
            ok = bool(res["auth"]) and res["resolver-a"] == [s["ip"]] and res["resolver-b"] == [s["ip"]]
            bad += not ok
            print(f"{'OK  ' if ok else 'FAIL'} {s['id']:<10} auth_soa={'yes' if res['auth'] else 'NO'} "
                  f"resolver-a={res['resolver-a']} resolver-b={res['resolver-b']}")
        sys.exit(1 if bad else 0)

    def serial0(sid: str) -> int:
        f = stand / "students" / sid / "serial0"
        return int(f.read_text()) if f.exists() else 0

    out_rows = []
    for s in students:
        z = f"{s['id']}.lab."
        ip = s["ip"]
        soa = rdata(dig(ip, z, "SOA"), "SOA")
        serial = int(soa[0].split()[2]) if soa else 0
        host2 = [r for r in dig(ip, f"{s['host2']}.{z}", "A") if r[3] == "A"]
        checks = {
            "zone_loaded": bool(soa),
            "serial_changed": serial > serial0(s["id"]),
            "www_A": set(rdata(dig(ip, f"www.{z}", "A"), "A")) & {"10.53.0.80", "10.53.0.81"} != set(),
            "alias_CNAME": rdata(dig(ip, f"{s['alias']}.{z}", "CNAME"), "CNAME") == [f"www.{z}"],
            "mail_A": rdata(dig(ip, f"mail.{z}", "A"), "A") == ["10.53.0.80"],
            "MX": rdata(dig(ip, z, "MX"), "MX") == [f"{s['mx_pref']} mail.{z}"],
            "TXT": f'"lab-token={s["token"]}"' in rdata(dig(ip, z, "TXT"), "TXT"),
            "host2_A_TTL": bool(host2) and host2[0][4] == "10.53.0.81" and host2[0][1] == str(s["ttl2"]),
            "www_moved_to_81": rdata(dig(ip, f"www.{z}", "A"), "A") == ["10.53.0.81"],
            "nx_created": bool(rdata(dig(ip, f"{s['nx']}.{z}", "A"), "A")),
        }
        passed = sum(checks.values())
        out_rows.append({"id": s["id"], "name": s["name"], "passed": f"{passed}/{len(checks)}",
                         **{k: int(v) for k, v in checks.items()}})
        marks = " ".join(("+" if v else "-") + k for k, v in checks.items())
        print(f"{s['id']:<10} {passed:>2}/{len(checks)}  {marks}")

    report = stand / "instructor/check-report.csv"
    with open(report, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nreport: {report}")


if __name__ == "__main__":
    main()
