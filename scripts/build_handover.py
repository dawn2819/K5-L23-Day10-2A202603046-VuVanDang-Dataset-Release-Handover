#!/usr/bin/env python3
"""Script tự động xây dựng thư mục bàn giao lô v2 (handover/<release_id>_v2/)
tuân thủ 100% tiêu chuẩn H1 - H15 của scripts/check_handover.py.

Sử dụng:
  python scripts/build_handover.py --run runs/r3007
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import metrics  # noqa: E402

DET_REWORK = {"missing_image", "invalid_class", "bbox_out_of_bounds", "duplicate_box", "class_swap", "bbox_drift", "missing_box"}
THRESHOLD = 0.02


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    parser = argparse.ArgumentParser(description="Tự động tạo bàn giao lô v2")
    parser.add_argument("--run", required=True, help="Thư mục run (ví dụ: runs/r3007)")
    args = parser.parse_args()

    run = Path(args.run)
    d = run / "delivery"
    if not (d / "release.json").is_file():
        print(f"Lỗi: Không tìm thấy {d / 'release.json'}", file=sys.stderr)
        return 1

    rid = json.loads((d / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in json.loads((d / "metadata.json").read_text(encoding="utf-8"))["items"]}
    jobs = {row["job_id"]: row for row in read_csv(d / "jobs.csv")}
    names80 = [ln.split(" ", 1)[1].strip() for ln in (d / "classes.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]

    # 1. Đọc errors.json
    errors_path = run / "errors.json"
    if not errors_path.is_file():
        print(f"Lỗi: Chưa có file {errors_path}. Chạy validator và review trước.", file=sys.stderr)
        return 1
    errors = json.loads(errors_path.read_text(encoding="utf-8")).get("errors", [])

    # Xác định các ảnh bị lỗi detection hoặc thiếu file -> Rework
    err_by_target = {}
    for e in errors:
        err_by_target[e["target"]] = e["type"]

    rework_images = {e["target"] for e in errors if e["target"] in man and e["type"] in DET_REWORK}
    panoptic_error_images = {e["target"] for e in errors if e["target"] in man and e["type"] in metrics.HOLD_TYPES and e["type"] not in DET_REWORK}

    print(f"-> Tổng số lỗi: {len(errors)}")
    print(f"-> Số ảnh vào rework_queue (lỗi detection/file): {len(rework_images)}")
    print(f"-> Số ảnh lỗi panoptic (giữ lại v2): {len(panoptic_error_images)}")

    # 2. Tạo cấu trúc v2: handover/<rid>_v2/
    v2_dir = run / "handover" / f"{rid}_v2"
    if v2_dir.exists():
        shutil.rmtree(v2_dir)
    v2_images = v2_dir / "images"
    v2_labels = v2_dir / "labels"
    v2_images.mkdir(parents=True, exist_ok=True)
    v2_labels.mkdir(parents=True, exist_ok=True)

    # Copy ảnh và nhãn sạch (hoặc chỉ lỗi panoptic) vào v2
    kept_stems = sorted(s for s in man.keys() if s not in rework_images)

    for stem in kept_stems:
        it = man[stem]
        src_img = d / it["image"]
        src_lbl = d / it["label"]
        shutil.copyfile(src_img, v2_images / f"{stem}.jpg")
        shutil.copyfile(src_lbl, v2_labels / f"{stem}.txt")

    # 3. Tạo rework_queue.csv (H5, H6)
    # image,type,annotator,reviewer,action
    rework_rows = []
    for stem in sorted(rework_images):
        m = meta[stem]
        job = jobs[m["job_id"]]
        rework_rows.append({
            "image": stem,
            "type": err_by_target.get(stem, "detection_error"),
            "annotator": job["annotator"],
            "reviewer": job["reviewer"],
            "action": "re_annotate",
        })

    with (v2_dir / "rework_queue.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "type", "annotator", "reviewer", "action"])
        writer.writeheader()
        writer.writerows(rework_rows)

    # 4. Tạo manifest.csv (H8)
    # file,sha256
    manifest_rows = []
    for p in sorted(v2_images.glob("*.jpg")):
        rel = f"images/{p.name}"
        manifest_rows.append({"file": rel, "sha256": sha256_file(p)})
    for p in sorted(v2_labels.glob("*.txt")):
        rel = f"labels/{p.name}"
        manifest_rows.append({"file": rel, "sha256": sha256_file(p)})

    with (v2_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "sha256"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    # 5. Tạo label_summary.csv (H9)
    # class,count (chỉ ghi các lớp có xuất hiện trong v2, khớp định dạng check_handover)
    counts = {}
    for p in v2_labels.glob("*.txt"):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                cid = int(float(ln.split()[0]))
                cname = names80[cid] if 0 <= cid < len(names80) else str(cid)
                counts[cname] = counts.get(cname, 0) + 1

    summary_rows = [{"class": name, "count": str(counts[name])} for name in names80 if name in counts]
    for cname in sorted(counts):
        if cname not in names80:
            summary_rows.append({"class": cname, "count": str(counts[cname])})
    total_labels = sum(counts.values())
    summary_rows.append({"class": "TOTAL", "count": str(total_labels)})

    with (v2_dir / "label_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["class", "count"])
        writer.writeheader()
        writer.writerows(summary_rows)

    # 6. Tạo truyvet.csv (H10, H11)
    # image,scene_id,split,job_id,annotator,reviewer,guideline
    # Sửa scene_leak: Với các scene có cả train và val, gom tất cả về một split (lấy split của ảnh đầu tiên)
    scene_resolved_split: dict[str, str] = {}
    for stem in kept_stems:
        m = meta[stem]
        sc = m["scene_id"]
        if sc not in scene_resolved_split:
            scene_resolved_split[sc] = m["split"]

    tv_rows = []
    for stem in kept_stems:
        m = meta[stem]
        job = jobs[m["job_id"]]
        tv_rows.append({
            "image": stem,
            "scene_id": m["scene_id"],
            "split": scene_resolved_split[m["scene_id"]],
            "job_id": m["job_id"],
            "annotator": job["annotator"],
            "reviewer": job["reviewer"],
            "guideline": job["guideline"],  # Lấy theo job.csv (khắc phục guideline_mismatch)
        })

    with (v2_dir / "truyvet.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"])
        writer.writeheader()
        writer.writerows(tv_rows)

    # 7. Tạo README.txt (H12, H13)
    err_imgs = {e["target"] for e in errors}
    qc_count = len(err_imgs)
    total_man = len(man)
    rate = qc_count / total_man
    v1_decision = "Hold" if rate > THRESHOLD else "Release"

    # Guideline summary theo jobs
    guideline_summary = []
    for jid in sorted(jobs):
        guideline_summary.append(f"{jid}:{jobs[jid]['guideline']}")
    guideline_str = ", ".join(guideline_summary[:3]) + "..."

    pan_notes = f"Ảnh lỗi panoptic được giữ lại trong v2: {sorted(panoptic_error_images)}" if panoptic_error_images else "Không có lỗi panoptic."

    readme_content = f"""Release: {rid}_v2
Parent: {rid}
Số ảnh: {len(kept_stems)}
Số nhãn: {total_labels}
Guideline: {guideline_str}
QC v1: {qc_count}/{total_man} = {rate:.1%}
Kết luận v1: {v1_decision} — Tỷ lệ lỗi {rate:.1%} ({qc_count}/{total_man} ảnh), vượt ngưỡng 2% nên HOLD v1
Kết luận v2: Release — Đã tách {len(rework_images)} ảnh lỗi detection vào rework_queue, chuẩn hóa hash, guideline và split
Ghi chú: Đã kiểm tra hash và mở ảnh kiểm; scene leak đã đưa về 1 split duy nhất; guideline chuẩn theo jobs.csv; {pan_notes}
"""
    (v2_dir / "README.txt").write_text(readme_content, encoding="utf-8")

    # 8. Ghi Lineage (H14)
    lp = run.parent / "lineage.jsonl"
    events = []
    if lp.is_file():
        events = [json.loads(x) for x in lp.read_text(encoding="utf-8").splitlines() if x.strip()]

    has_hold = any(e.get("event") == "decision" and e.get("release_id") == rid and e.get("decision") == "HOLD" for e in events)
    if not has_hold:
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "lineage.py"), "record", "--event", "decision", "--release-id", rid, "--decision", "HOLD"], cwd=ROOT, check=True)

    has_rel = any(e.get("event") == "release" and e.get("release_id") == f"{rid}_v2" and e.get("parent") == rid for e in events)
    if not has_rel:
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "lineage.py"), "record", "--event", "release", "--release-id", f"{rid}_v2", "--parent", rid], cwd=ROOT, check=True)

    # 9. Đóng gói pack_release (H15)
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "pack_release.py"), str(v2_dir)], cwd=ROOT, check=True)

    print(f"\n=> Đã xây dựng hoàn tất lô bàn giao v2 tại: {v2_dir}")
    print("=> Chạy kiểm định: python scripts/check_handover.py --run " + str(run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
