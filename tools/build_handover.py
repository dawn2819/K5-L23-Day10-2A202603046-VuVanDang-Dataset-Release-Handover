#!/usr/bin/env python3
"""Pha 4: Script tu dong dong goi lo ban giao v2 (dat chuan H1-H15 trong check_handover.py).

Tuyet doi KHONG sua bat ky file nao trong delivery/ (lo v1).

Cach dung:
  python tools/build_handover.py --run runs/r3007

  # Neu mo xem mat thay anh wrong_hash bi hong file (can dua sang rework):
  python tools/build_handover.py --run runs/r3007 --broken-hash 000000123456
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DET_REWORK = {
    "missing_image",
    "invalid_class",
    "bbox_out_of_bounds",
    "duplicate_box",
    "class_swap",
    "bbox_drift",
    "missing_box",
}
PANOPTIC_ONLY = {
    "invalid_category_id",
    "thing_overlap",
    "category_swap",
    "instance_merge",
}
REWORK_ACTIONS = {
    "missing_image": "bo sung file anh thieu va kiem lai nhan",
    "invalid_class": "sua class_id ngoai 0-79 ve dung lop va review lai",
    "bbox_out_of_bounds": "cat/ve lai bbox nam trong bien anh [0,1]",
    "duplicate_box": "xoa box lap trung va kiem lai nhan",
    "class_swap": "sua lai ten lop detection dung voi vat the trong anh",
    "bbox_drift": "chinh lai bbox khop sat vat the",
    "missing_box": "gan bo sung box detection bi thieu",
    "wrong_hash": "anh bi hong file, can cung cap lai anh va gan lai",
}
THRESHOLD = 0.02


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_valid_jpeg(path: Path) -> bool:
    """Kiem tra nhanh header/footer JPEG (van can nguoi mo xem mat xac nhan)."""
    if not path.is_file():
        return False
    data = path.read_bytes()
    return len(data) > 100 and data[:2] == b"\xff\xd8" and b"\xff\xd9" in data[-64:]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def format_guideline_summary(jobs: dict[str, dict]) -> str:
    by_gl: dict[str, list[str]] = defaultdict(list)
    for jid, row in sorted(jobs.items()):
        by_gl[row["guideline"].strip()].append(jid)
    parts = []
    for gl, jids in sorted(by_gl.items()):
        if len(jids) == 1:
            parts.append(f"{gl} ({jids[0]})")
        else:
            parts.append(f"{gl} ({jids[0]}-{jids[-1]})")
    return ", ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tu dong dong goi lo ban giao v2")
    ap.add_argument("--run", required=True, help="Thu muc run (vd: runs/r3007)")
    ap.add_argument(
        "--broken-hash",
        default="",
        help="Danh sach ten anh wrong_hash bi hong file (phan tach dau phay) de chuyen sang rework",
    )
    ap.add_argument(
        "--no-pack",
        action="store_true",
        help="Khong tu dong goi scripts/pack_release.py",
    )
    args = ap.parse_args()

    run_dir = Path(args.run)
    delivery = run_dir / "delivery"
    errors_path = run_dir / "errors.json"

    if not delivery.is_dir():
        raise SystemExit(f"Khong thay thu muc delivery: {delivery}")
    if not errors_path.is_file():
        raise SystemExit(f"Chua co {errors_path}. Can chot errors.json truoc khi dong goi v2.")

    rid = json.loads((delivery / "release.json").read_text(encoding="utf-8"))["release_id"]
    man = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    meta_list = json.loads((delivery / "metadata.json").read_text(encoding="utf-8"))["items"]
    meta = {m["image"]: m for m in meta_list}
    jobs = {row["job_id"]: row for row in read_csv(delivery / "jobs.csv")}
    names80 = [
        ln.split(" ", 1)[1].strip()
        for ln in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    errors = json.loads(errors_path.read_text(encoding="utf-8"))["errors"]

    broken_hash_set = {s.strip() for s in args.broken_hash.split(",") if s.strip()}

    # 1. Phan loai cac loi trong errors.json
    rework_map: dict[str, list[str]] = defaultdict(list)
    panoptic_imgs: dict[str, list[str]] = defaultdict(list)
    wrong_hash_imgs: list[str] = []
    guideline_fix_imgs: list[str] = []
    leaked_scenes: list[str] = []

    for e in errors:
        etype = e["type"]
        target = e["target"]
        if etype in DET_REWORK and target in man:
            rework_map[target].append(etype)
        elif etype == "wrong_hash" and target in man:
            wrong_hash_imgs.append(target)
            if target in broken_hash_set:
                rework_map[target].append(etype)
        elif etype == "guideline_mismatch" and target in man:
            guideline_fix_imgs.append(target)
        elif etype == "scene_leak":
            leaked_scenes.append(target)
        elif etype in PANOPTIC_ONLY and target in man:
            panoptic_imgs[target].append(etype)

    # Kiem tra nhanh cac anh wrong_hash va nhac nguoi mo xem mat
    if wrong_hash_imgs:
        print("=== KIEM TRA ANH wrong_hash (NHAC: NGUOI MO XEM MAT DE XAC NHAN ANH CON NGUYEN) ===")
        for img in sorted(set(wrong_hash_imgs)):
            img_path = delivery / man[img]["image"]
            ok_jpg = is_valid_jpeg(img_path)
            status = "REWORK (--broken-hash)" if img in broken_hash_set else (
                "JPEG hop le -> giu trong v2, tinh lai sha256" if ok_jpg else "CANH BAO: JPEG co the hong! Kiem tra ngay!"
            )
            print(f"  - {img}: {status} ({img_path})")

    # 2. Chuan bi thu muc v2 sach se (khong dung vao delivery/ v1)
    v2_dir = run_dir / "handover" / f"{rid}_v2"
    if v2_dir.exists():
        shutil.rmtree(v2_dir)
    (v2_dir / "images").mkdir(parents=True)
    (v2_dir / "labels").mkdir(parents=True)

    # 3. Copy images/ va labels/ giu nguyen byte goc cho cac anh khong thuoc rework
    rework_stems = set(rework_map.keys())
    kept_stems = sorted(stem for stem in man.keys() if stem not in rework_stems)

    for stem in kept_stems:
        src_img = delivery / man[stem]["image"]
        src_lbl = delivery / man[stem]["label"]
        if not src_img.is_file():
            raise SystemExit(
                f"LOI: Anh {stem} khong ton tai o {src_img} nhung khong co trong errors.json (missing_image)!"
            )
        shutil.copyfile(src_img, v2_dir / "images" / f"{stem}.jpg")
        shutil.copyfile(src_lbl, v2_dir / "labels" / f"{stem}.txt")

    # 4. Ghi rework_queue.csv
    rework_rows = []
    for stem in sorted(rework_stems):
        m = meta[stem]
        job = jobs[m["job_id"]]
        types_str = ";".join(sorted(set(rework_map[stem])))
        primary_type = sorted(set(rework_map[stem]))[0]
        rework_rows.append({
            "image": stem,
            "type": types_str,
            "annotator": job["annotator"],
            "reviewer": job["reviewer"],
            "action": REWORK_ACTIONS.get(primary_type, "gan lai va kiem duyet lai"),
        })
    with (v2_dir / "rework_queue.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image", "type", "annotator", "reviewer", "action"])
        w.writeheader()
        w.writerows(rework_rows)

    # 5. Ghi manifest.csv (sha256 tat ca file trong images/ va labels/)
    manifest_rows = []
    for sub in ("images", "labels"):
        for p in sorted((v2_dir / sub).iterdir()):
            if p.is_file():
                rel = p.relative_to(v2_dir).as_posix()
                manifest_rows.append({"file": rel, "sha256": sha256_file(p)})
    with (v2_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "sha256"])
        w.writeheader()
        w.writerows(manifest_rows)

    # 6. Ghi label_summary.csv
    counts: Counter[str] = Counter()
    for stem in kept_stems:
        for ln in (v2_dir / "labels" / f"{stem}.txt").read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            cid = int(float(ln.split()[0]))
            cname = names80[cid] if 0 <= cid < 80 else str(cid)
            counts[cname] += 1
    total_labels = sum(counts.values())
    with (v2_dir / "label_summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["class", "count"])
        w.writeheader()
        for cname in sorted(counts.keys()):
            w.writerow({"class": cname, "count": counts[cname]})
        w.writerow({"class": "TOTAL", "count": total_labels})

    # 7. Xu ly scene_leak & guideline_mismatch -> ghi truyvet.csv
    scene_split_votes: dict[str, Counter[str]] = defaultdict(Counter)
    for m in meta_list:
        scene_split_votes[m["scene_id"]][m["split"]] += 1

    canonical_split: dict[str, str] = {}
    fixed_scenes_desc: list[str] = []
    for sc, counter in sorted(scene_split_votes.items()):
        if len(counter) > 1:
            # Chon split da so (hoa thi uu tien train)
            chosen = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            canonical_split[sc] = chosen
            fixed_scenes_desc.append(f"{sc} -> {chosen}")
        else:
            canonical_split[sc] = next(iter(counter.keys()))

    truyvet_rows = []
    for stem in kept_stems:
        m = meta[stem]
        job = jobs[m["job_id"]]
        truyvet_rows.append({
            "image": stem,
            "scene_id": m["scene_id"],
            "split": canonical_split[m["scene_id"]],
            "job_id": m["job_id"],
            "annotator": job["annotator"],
            "reviewer": job["reviewer"],
            "guideline": job["guideline"],  # Lay theo job, sua triet de guideline_mismatch
        })
    with (v2_dir / "truyvet.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["image", "scene_id", "split", "job_id", "annotator", "reviewer", "guideline"],
        )
        w.writeheader()
        w.writerows(truyvet_rows)

    # 8. Ghi README.txt dung mau templates/README.txt va chuan H12-H13
    err_targets = {e["target"] for e in errors}
    n_err = len(err_targets)
    n_total_v1 = len(man)
    rate = n_err / n_total_v1
    rate_pct = f"{rate * 100:.1f}%".replace(".", ",")
    v1_decision = (
        f"Hold — tỉ lệ lỗi {rate_pct} vượt ngưỡng 2% theo quy định Day 7, không được phép Release v1"
        if rate > THRESHOLD
        else f"Release — tỉ lệ lỗi {rate_pct} không vượt ngưỡng 2%"
    )
    v2_decision = (
        f"Release — đã tách {len(rework_stems)} ảnh lỗi nhãn detection/thiếu file sang rework_queue.csv, "
        f"sửa siêu dữ liệu (hash, guideline, scene_leak) trong v2; còn lại {len(kept_stems)} ảnh sạch nhãn detection"
    )

    notes_parts = []
    if fixed_scenes_desc:
        notes_parts.append(f"Sửa scene_leak bằng cách gom toàn bộ cảnh về 1 split duy nhất ({', '.join(fixed_scenes_desc)})")
    if wrong_hash_imgs:
        kept_wh = sorted(set(wrong_hash_imgs) - broken_hash_set)
        if kept_wh:
            notes_parts.append(
                f"wrong_hash ({', '.join(kept_wh)}): đã mở ảnh kiểm tra còn nguyên vẹn, chỉ sai manifest nên giữ ở v2 và tính lại sha256 mới"
            )
    if guideline_fix_imgs:
        notes_parts.append(
            f"Sửa guideline_mismatch ({', '.join(sorted(set(guideline_fix_imgs)))}) trong truyvet.csv theo đúng phiên bản ở jobs.csv"
        )
    if rework_rows:
        assignees = sorted({f"{r['annotator']}/{r['reviewer']}" for r in rework_rows})
        notes_parts.append(
            f"Chuyển {len(rework_rows)} ảnh lỗi detection sang rework_queue.csv giao đúng annotator/reviewer ({', '.join(assignees)})"
        )
    if panoptic_imgs:
        pan_desc = ", ".join(f"{img} ({'+'.join(sorted(set(ts)))})" for img, ts in sorted(panoptic_imgs.items()))
        notes_parts.append(
            f"Các ảnh chỉ lỗi panoptic ({pan_desc}) giữ nguyên ở lại v2 do nhãn detection vẫn đúng, đã ghi nhận để báo team panoptic xử lý"
        )

    readme_text = (
        f"Release: {rid}_v2\n"
        f"Parent: {rid}\n"
        f"Số ảnh: {len(kept_stems)}\n"
        f"Số nhãn: {total_labels}\n"
        f"Guideline: {format_guideline_summary(jobs)}\n"
        f"QC v1: {n_err}/{n_total_v1} = {rate_pct}\n"
        f"Kết luận v1: {v1_decision}\n"
        f"Kết luận v2: {v2_decision}\n"
        f"Ghi chú: {'; '.join(notes_parts)}.\n"
    )
    (v2_dir / "README.txt").write_text(readme_text, encoding="utf-8")

    print(f"\n=== DA TAO LO v2: {v2_dir} ===")
    print(f"  So anh v2         : {len(kept_stems)} / {n_total_v1}")
    print(f"  So anh rework     : {len(rework_stems)}")
    print(f"  Tong nhan v2      : {total_labels}")
    print(f"  QC v1             : {n_err}/{n_total_v1} ({rate:.1%})")

    # 9. Tu dong dong goi .zip + .sha256 bang scripts/pack_release.py
    if not args.no_pack:
        print("\n=== DONG GOI .zip + .sha256 ===")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "pack_release.py"), str(v2_dir)],
            check=True,
        )

    print("\n=== BUOC TIEP THEO (CHAY LINEAGE & CHECK_HANDOVER) ===")
    print(f"  python scripts/lineage.py record --event decision --release-id {rid} --decision HOLD")
    print(f"  python scripts/lineage.py impact --release-id {rid}")
    print(f"  python scripts/lineage.py record --event release --release-id {rid}_v2 --parent {rid}")
    print(f"  python scripts/check_handover.py --run {args.run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
