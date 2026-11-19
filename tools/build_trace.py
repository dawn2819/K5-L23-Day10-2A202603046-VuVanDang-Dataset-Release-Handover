#!/usr/bin/env python3
"""Pha 5 & De an: Tu dong truy vet ticket team AI va xuat trace.json.

Cach dung:
  # Seed luyen tap:
  python tools/build_trace.py runs/r3007/delivery --out runs/r3007/trace.json

  # De an:
  python tools/build_trace.py delivery --out submission/de_an/trace.json

  # Neu can chi dinh thu cong (phong truong hop de an doi format van ban):
  python tools/build_trace.py delivery --out submission/de_an/trace.json ^
      --rule-class person --old-guideline v1.2 --scenes scene_101,scene_202
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def read_classes(delivery: Path) -> dict[str, int]:
    """Doc classes.txt -> map ten lop -> class_id (0..79)."""
    name_to_id: dict[str, int] = {}
    for line in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        cid_str, cname = line.split(" ", 1)
        name_to_id[cname.strip()] = int(cid_str)
    return name_to_id


def parse_changelog(changelog_text: str, valid_classes: set[str]) -> tuple[str | None, str | None]:
    """Trich xuat (rule_class, old_guideline) tu guideline/changelog.md."""
    rule_class = None
    for m in re.finditer(r"`([^`]+)`", changelog_text):
        cand = m.group(1).strip()
        if cand in valid_classes:
            rule_class = cand
            break

    # Tim cac phien ban dang ## v1.3, ## v1.2 hoac v1.x trong changelog
    versions = re.findall(r"\bv\d+\.\d+\b", changelog_text)
    unique_versions = sorted(set(versions), key=lambda v: [int(x) for x in v[1:].split(".")])
    old_guideline = unique_versions[0] if len(unique_versions) >= 2 else None
    return rule_class, old_guideline


def parse_ticket(ticket_text: str, valid_classes: set[str]) -> tuple[list[str], str | None]:
    """Trich xuat (reported_scenes, rule_class) tu incoming/ticket.md."""
    scenes = sorted(set(re.findall(r"\bscene_[A-Za-z0-9_-]+\b", ticket_text)))
    rule_class = None
    for m in re.finditer(r"`([^`]+)`", ticket_text):
        cand = m.group(1).strip()
        if cand in valid_classes:
            rule_class = cand
            break
    return scenes, rule_class


def image_has_class(label_path: Path, target_class_id: int) -> bool:
    """Kiem tra file labels/<image>.txt co it nhat 1 box detection thuoc target_class_id."""
    if not label_path.is_file():
        return False
    for line in label_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        try:
            cid = int(float(parts[0]))
        except (ValueError, IndexError):
            continue
        if cid == target_class_id:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Truy vet ticket team AI -> trace.json")
    ap.add_argument("delivery", help="Thu muc delivery (vd: runs/r3007/delivery hoac delivery)")
    ap.add_argument("--out", required=True, help="File trace.json dau ra")
    ap.add_argument("--rule-class", help="Override ten lop bi doi quy tac (vd: car)")
    ap.add_argument("--old-guideline", help="Override phien ban guideline cu (vd: v1.2)")
    ap.add_argument("--scenes", help="Override danh sach scene_id team AI bao, phan tach bang dau phay")
    args = ap.parse_args()

    delivery = Path(args.delivery)
    if not delivery.is_dir():
        raise SystemExit(f"Khong tim thay thu muc delivery: {delivery}")

    name_to_id = read_classes(delivery)
    valid_classes = set(name_to_id.keys())

    changelog_text = (delivery / "guideline" / "changelog.md").read_text(encoding="utf-8")
    ticket_text = (delivery / "incoming" / "ticket.md").read_text(encoding="utf-8")

    cl_class, cl_old_gl = parse_changelog(changelog_text, valid_classes)
    tk_scenes, tk_class = parse_ticket(ticket_text, valid_classes)

    with (delivery / "jobs.csv").open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}

    # Neu changelog khong co >= 2 version, lay version nho nhat trong jobs.csv
    if not cl_old_gl:
        job_versions = sorted(
            {j["guideline"].strip() for j in jobs.values() if j.get("guideline")},
            key=lambda v: [int(x) for x in re.findall(r"\d+", v)] or [0],
        )
        cl_old_gl = job_versions[0] if job_versions else "v1.2"

    rule_class = args.rule_class or cl_class or tk_class
    old_guideline = args.old_guideline or cl_old_gl
    reported_scenes = (
        [s.strip() for s in args.scenes.split(",") if s.strip()]
        if args.scenes
        else tk_scenes
    )

    print("=== NOI DUNG changelog.md ===")
    print(changelog_text.strip())
    print("\n=== NOI DUNG ticket.md ===")
    print(ticket_text.strip())
    print("\n=== THONG SO TRICH XUAT (KIEM TRA BANG MAT!) ===")
    print(f"  Lop bi doi quy tac : {rule_class} (class_id={name_to_id.get(rule_class)})")
    print(f"  Guideline cu       : {old_guideline}")
    print(f"  Cac scene AI bao   : {reported_scenes}")

    if not rule_class or rule_class not in name_to_id:
        raise SystemExit("LOI: Khong xac dinh duoc rule_class hop le. Hay truyen --rule-class <ten_lop>.")
    if not reported_scenes:
        raise SystemExit("LOI: Khong tim thay scene_id nao trong ticket.md. Hay truyen --scenes scene_xxx,...")

    target_cid = name_to_id[rule_class]
    reported_set = set(reported_scenes)

    meta_items = json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))["items"]
    manifest_items = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]

    tier_a: list[str] = []
    tier_b: list[str] = []
    affected_jobs: set[str] = set()

    for m in meta_items:
        img = m["image"]
        job_id = m["job_id"]
        job = jobs.get(job_id)
        if not job:
            continue
        # QUAN TRONG: dung guideline cua JOB trong jobs.csv, KHONG dung metadata.json
        if job["guideline"].strip() != old_guideline:
            continue
        lbl_rel = manifest_items.get(img, {}).get("label", f"labels/{img}.txt")
        if not image_has_class(delivery / lbl_rel, target_cid):
            continue

        affected_jobs.add(job_id)
        if m["scene_id"] in reported_set:
            tier_a.append(img)
        else:
            tier_b.append(img)

    tier_a.sort()
    tier_b.sort()
    notify = sorted(
        {jobs[jid]["annotator"].strip() for jid in affected_jobs}
        | {jobs[jid]["reviewer"].strip() for jid in affected_jobs}
    )

    result = {
        "tier_a": tier_a,
        "tier_b": tier_b,
        "notify": notify,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n=== KET QUA trace.json ===")
    print(f"  tier_a ({len(tier_a)} anh) : {tier_a}")
    print(f"  tier_b ({len(tier_b)} anh) : {tier_b[:10]}{' ...' if len(tier_b) > 10 else ''}")
    print(f"  notify ({len(notify)} nguoi): {notify}")
    print(f"  affected_jobs      : {sorted(affected_jobs)}")
    print(f"=> Da ghi {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
