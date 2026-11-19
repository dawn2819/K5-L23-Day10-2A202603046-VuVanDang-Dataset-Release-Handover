#!/usr/bin/env python3
"""Script tự động giải bài toán truy vết (Traceability) cho Pha 5.

Đọc ticket.md và changelog.md trong delivery, xác định rule_class và các scene bị báo lỗi,
sau đó trích xuất tier_a, tier_b và notify theo đúng tiêu chuẩn.

Sử dụng:
  python scripts/solve_trace.py --run runs/r3007
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Tự động trích xuất trace.json")
    parser.add_argument("--run", required=True, help="Thư mục run (ví dụ: runs/r3007)")
    args = parser.parse_args()

    run = Path(args.run)
    d = run / "delivery"

    ticket_path = d / "incoming" / "ticket.md"
    changelog_path = d / "guideline" / "changelog.md"
    metadata_path = d / "metadata.json"
    jobs_path = d / "jobs.csv"
    classes_path = d / "classes.txt"

    if not (ticket_path.is_file() and changelog_path.is_file()):
        print(f"Lỗi: Thiếu ticket.md hoặc changelog.md trong {d}", file=sys.stderr)
        return 1

    ticket_text = ticket_path.read_text(encoding="utf-8")
    changelog_text = changelog_path.read_text(encoding="utf-8")

    # 1. Tìm lớp bị đổi quy tắc từ changelog.md
    m_class = re.search(r"Lớp `([^`]+)`", changelog_text)
    if not m_class:
        m_class = re.search(r"lớp `([^`]+)`", changelog_text, re.I)
    if not m_class:
        print("Lỗi: Không tìm thấy tên lớp trong changelog.md", file=sys.stderr)
        return 1
    rule_class = m_class.group(1).strip()

    # 2. Tìm các scene được team AI báo lỗi trong ticket.md
    reported_scenes = set(re.findall(r"scene_\w+", ticket_text))

    print(f"-> Lớp bị đổi quy tắc: '{rule_class}'")
    print(f"-> Các scene team AI báo lỗi: {sorted(reported_scenes)}")

    # 3. Đọc classes.txt để lấy class_id của rule_class
    names80 = [ln.split(" ", 1)[1].strip() for ln in classes_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if rule_class not in names80:
        print(f"Lỗi: Lớp '{rule_class}' không có trong classes.txt", file=sys.stderr)
        return 1
    target_cls_id = names80.index(rule_class)

    # 4. Đọc jobs.csv
    with jobs_path.open(encoding="utf-8", newline="") as f:
        jobs = {row["job_id"]: row for row in csv.DictReader(f)}

    # 5. Đọc metadata.json
    metadata = {m["image"]: m for m in json.loads(metadata_path.read_text(encoding="utf-8"))["items"]}

    # 6. Lọc các ảnh thuộc job guideline cũ (v1.2 theo jobs.csv) và có ít nhất 1 box detection của rule_class
    has_target_images = []
    for stem, m in metadata.items():
        job = jobs.get(m["job_id"])
        if not job or job.get("guideline") != "v1.2":
            continue

        lbl_file = d / "labels" / f"{stem}.txt"
        if not lbl_file.is_file():
            continue

        has_class = False
        for line in lbl_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.strip().split()
            if int(float(parts[0])) == target_cls_id:
                has_class = True
                break

        if has_class:
            has_target_images.append(m)

    tier_a = sorted(m["image"] for m in has_target_images if m["scene_id"] in reported_scenes)
    tier_b = sorted(m["image"] for m in has_target_images if m["scene_id"] not in reported_scenes)

    involved_jobs = {m["job_id"] for m in has_target_images}
    notify = sorted({jobs[j]["annotator"] for j in involved_jobs} | {jobs[j]["reviewer"] for j in involved_jobs})

    trace_doc = {
        "tier_a": tier_a,
        "tier_b": tier_b,
        "notify": notify,
    }

    out_path = run / "trace.json"
    out_path.write_text(json.dumps(trace_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"-> Đã ghi trace.json: tier_a={len(tier_a)} ảnh, tier_b={len(tier_b)} ảnh, notify={len(notify)} người tại: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
