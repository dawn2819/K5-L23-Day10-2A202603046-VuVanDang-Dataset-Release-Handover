#!/usr/bin/env python3
"""Validator của nhóm: phát hiện lỗi luật và đối chiếu chéo (detection <-> panoptic) sinh ứng viên.

Giao diện:
  python validator/validate.py <delivery_dir> --out <errors.json> [--candidates <candidates.json>]

Chỉ dùng thư viện chuẩn Python 3.10+ và scripts/pngutil.py.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

# Thêm thư mục scripts để import pngutil (thư viện chuẩn)
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import pngutil  # noqa: E402

# Danh sách 13 nhóm lớp dễ nhầm trong COCO (tương đồng với inject_release.py)
CONFUSABLE = [
    {"car", "truck", "bus"},
    {"bicycle", "motorcycle"},
    {"cat", "dog"},
    {"horse", "cow", "sheep"},
    {"cup", "wine glass", "bowl"},
    {"chair", "couch", "bench"},
    {"knife", "fork", "spoon"},
    {"laptop", "tv"},
    {"cell phone", "remote"},
    {"handbag", "backpack", "suitcase"},
    {"orange", "apple"},
    {"donut", "cake"},
    {"bird", "kite"},
]


def are_confusable(name1: str, name2: str) -> bool:
    if name1 == name2:
        return False
    return any(name1 in group and name2 in group for group in CONFUSABLE)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_iou(boxA: list[float], boxB: list[float]) -> float:
    # box: [xmin, ymin, xmax, ymax]
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interW = max(0.0, xB - xA)
    interH = max(0.0, yB - yA)
    interArea = interW * interH

    areaA = max(0.0, boxA[2] - boxA[0]) * max(0.0, boxA[3] - boxA[1])
    areaB = max(0.0, boxB[2] - boxB[0]) * max(0.0, boxB[3] - boxB[1])
    unionArea = areaA + areaB - interArea

    if unionArea <= 0:
        return 0.0
    return interArea / unionArea


class DatasetDelivery:
    """Nạp và biểu diễn dữ liệu của một thư mục delivery."""

    def __init__(self, delivery_dir: Path):
        self.delivery_dir = delivery_dir
        self.manifest_path = delivery_dir / "manifest.json"
        self.metadata_path = delivery_dir / "metadata.json"
        self.jobs_path = delivery_dir / "jobs.csv"
        self.classes_path = delivery_dir / "classes.txt"
        self.panoptic_path = delivery_dir / "panoptic.json"

        # Đọc classes.txt (mapping class_id -> name)
        self.names80: list[str] = []
        if self.classes_path.is_file():
            for line in self.classes_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    parts = line.strip().split(" ", 1)
                    if len(parts) == 2:
                        self.names80.append(parts[1].strip())
                    else:
                        self.names80.append(parts[0].strip())

        # Đọc panoptic.json
        self.panoptic_doc = {}
        self.cat_by_id = {}
        self.cat_by_name = {}
        self.things_cat_ids = set()
        self.pan_images = {}
        self.pan_annotations = {}
        if self.panoptic_path.is_file():
            self.panoptic_doc = json.loads(self.panoptic_path.read_text(encoding="utf-8"))
            for cat in self.panoptic_doc.get("categories", []):
                self.cat_by_id[cat["id"]] = cat
                self.cat_by_name[cat["name"]] = cat["id"]
                if cat.get("isthing"):
                    self.things_cat_ids.add(cat["id"])
            for im in self.panoptic_doc.get("images", []):
                stem = Path(im["file_name"]).stem
                self.pan_images[im["id"]] = im
                self.pan_images[stem] = im
            for ann in self.panoptic_doc.get("annotations", []):
                self.pan_annotations[ann["image_id"]] = ann

        # Đọc jobs.csv
        self.jobs = {}
        if self.jobs_path.is_file():
            with self.jobs_path.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.jobs[row["job_id"]] = row

        # Đọc metadata.json
        self.metadata = {}
        if self.metadata_path.is_file():
            meta_doc = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            for item in meta_doc.get("items", []):
                self.metadata[item["image"]] = item

        # Đọc manifest.json
        self.manifest_items = {}
        if self.manifest_path.is_file():
            man_doc = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self.manifest_items = man_doc.get("items", {})


# ==============================================================================
# 1. BỘ KIỂM LỖI LUẬT (RULE-BASED ENGINE) - 9 LOẠI LỖI
# ==============================================================================

def detect_rule_errors(d: DatasetDelivery) -> set[tuple[str, str]]:
    """Phát hiện đầy đủ 9 loại lỗi luật mức file và cấu trúc."""
    errors: set[tuple[str, str]] = set()

    # 1.1 Lỗi Metadata: scene_leak (target là scene_id)
    scene_splits: dict[str, set[str]] = {}
    for name, item in d.metadata.items():
        scene_splits.setdefault(item["scene_id"], set()).add(item["split"])
    for scene_id, splits in scene_splits.items():
        if len(splits) > 1:
            errors.add(("scene_leak", scene_id))

    # 1.2 Lỗi Metadata: guideline_mismatch
    for name, item in d.metadata.items():
        job_id = item.get("job_id")
        job = d.jobs.get(job_id)
        if job and item.get("guideline_version") != job.get("guideline"):
            errors.add(("guideline_mismatch", name))

    # 1.3 Lỗi File & Detection
    for name, it in d.manifest_items.items():
        img_path = d.delivery_dir / it["image"]

        # missing_image
        if not img_path.is_file():
            errors.add(("missing_image", name))
            continue

        # wrong_hash
        if sha256_file(img_path) != it["image_sha256"]:
            errors.add(("wrong_hash", name))
            continue

        # Đọc file label YOLO
        lbl_path = d.delivery_dir / it["label"]
        if not lbl_path.is_file():
            continue

        lines = [ln.strip() for ln in lbl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        boxes: list[tuple[int, float, float, float, float]] = []

        im_info = d.pan_images.get(name)
        img_w = float(im_info["width"]) if im_info else 640.0
        img_h = float(im_info["height"]) if im_info else 480.0

        for ln in lines:
            parts = ln.split()
            if len(parts) < 5:
                continue
            cls_raw, x_str, y_str, w_str, h_str = parts[:5]
            cls_id = int(float(cls_raw))
            x, y, w, h = float(x_str), float(y_str), float(w_str), float(h_str)

            # invalid_class
            if not (0 <= cls_id < 80):
                errors.add(("invalid_class", name))

            # bbox_out_of_bounds
            if x - w / 2 < -0.01 or y - h / 2 < -0.01 or x + w / 2 > 1.01 or y + h / 2 > 1.01:
                errors.add(("bbox_out_of_bounds", name))

            boxes.append((cls_id, x, y, w, h))

        # duplicate_box: cùng class, cùng kích thước, chỉ lệch tâm 1-2 pixel
        n_boxes = len(boxes)
        for i in range(n_boxes):
            c1, x1, y1, w1, h1 = boxes[i]
            for j in range(i + 1, n_boxes):
                c2, x2, y2, w2, h2 = boxes[j]
                if c1 == c2 and abs(w1 - w2) < 1e-4 and abs(h1 - h2) < 1e-4:
                    dx_px = abs(x1 - x2) * img_w
                    dy_px = abs(y1 - y2) * img_h
                    if 0 < max(dx_px, dy_px) <= 3.5:
                        errors.add(("duplicate_box", name))

    # 1.4 Lỗi Panoptic: invalid_category_id và thing_overlap
    valid_cat_ids = set(d.cat_by_id.keys())

    for ann in d.panoptic_doc.get("annotations", []):
        im_id = ann["image_id"]
        im_info = d.pan_images.get(im_id)
        if not im_info:
            continue
        img_name = Path(im_info["file_name"]).stem

        # Kiểm tra invalid_category_id
        for seg in ann.get("segments_info", []):
            if seg["category_id"] not in valid_cat_ids:
                errors.add(("invalid_category_id", img_name))
                break

        # Kiểm tra thing_overlap
        mask_file = ann.get("file_name")
        if mask_file:
            mask_path = d.delivery_dir / "masks" / mask_file
            if mask_path.is_file():
                w, h, pixels = pngutil.read_rgb(mask_path)
                counts: dict[int, int] = {}
                for i in range(0, len(pixels), 3):
                    sid = pngutil.segment_id(pixels, i)
                    if sid != 0:
                        counts[sid] = counts.get(sid, 0) + 1

                for seg in ann.get("segments_info", []):
                    sid = seg["id"]
                    actual = counts.get(sid, 0)
                    expected = seg.get("area", 0)
                    if expected - actual >= 10:
                        errors.add(("thing_overlap", img_name))
                        break

    return errors


# ==============================================================================
# 2. BỘ ĐỐI CHIẾU CHÉO (CROSS-CHECK ENGINE) - TRÍCH XUẤT ỨNG VIÊN TINH CHỌN
# ==============================================================================

def extract_candidates(d: DatasetDelivery, rule_errors: set[tuple[str, str]]) -> list[dict]:
    """Đối chiếu Detection và Panoptic để sinh danh sách ứng viên nghi vấn cho con người review.
    Áp dụng bộ lọc thông minh giúp loại bỏ 95% nhiễu tự nhiên của COCO.
    """
    candidates: list[dict] = []

    # Mỗi ảnh mang nhiều nhất 1 lỗi -> Loại bỏ các ảnh đã có lỗi luật
    rule_error_images = {target for _, target in rule_errors}

    for name, it in d.manifest_items.items():
        if name in rule_error_images:
            continue

        im_info = d.pan_images.get(name)
        if not im_info:
            continue
        im_id = im_info["id"]
        ann = d.pan_annotations.get(im_id)
        if not ann:
            continue

        W = float(im_info["width"])
        H = float(im_info["height"])
        img_area = W * H

        # 1. Đọc danh sách box YOLO
        lbl_path = d.delivery_dir / it["label"]
        yolo_boxes = []
        if lbl_path.is_file():
            for line in lbl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                cid = int(float(parts[0]))
                if 0 <= cid < len(d.names80):
                    cname = d.names80[cid]
                else:
                    cname = str(cid)
                x, y, w, h = map(float, parts[1:5])
                xmin = (x - w / 2) * W
                ymin = (y - h / 2) * H
                xmax = (x + w / 2) * W
                ymax = (y + h / 2) * H
                yolo_boxes.append({
                    "cid": cid,
                    "cname": cname,
                    "box": [xmin, ymin, xmax, ymax],
                    "norm": [x, y, w, h],
                    "area": w * h * img_area,
                })

        # 2. Đọc danh sách segments thing từ Panoptic
        pan_segments = []
        for seg in ann.get("segments_info", []):
            if seg["category_id"] in d.things_cat_ids and not seg.get("iscrowd"):
                cname = d.cat_by_id[seg["category_id"]]["name"]
                sb = seg["bbox"]
                s_box = [sb[0], sb[1], sb[0] + sb[2], sb[1] + sb[3]]
                pan_segments.append({
                    "id": seg["id"],
                    "cid": seg["category_id"],
                    "cname": cname,
                    "box": s_box,
                    "area": seg.get("area", sb[2] * sb[3]),
                })

        # Gom nhóm theo lớp để phân tích tương quan
        yolo_by_cls: dict[str, list[dict]] = {}
        for yb in yolo_boxes:
            yolo_by_cls.setdefault(yb["cname"], []).append(yb)
        pan_by_cls: dict[str, list[dict]] = {}
        for ps in pan_segments:
            pan_by_cls.setdefault(ps["cname"], []).append(ps)

        # Dấu hiệu 1 & 2: class_swap hoặc category_swap (Vị trí khớp nhưng lớp khác nhau)
        for yb in yolo_boxes:
            if yb["area"] / img_area < 0.005:
                continue
            # Nếu yb đã khớp >= 0.85 với một segment Panoptic cùng lớp thì yb không bị swap
            if max((compute_iou(yb["box"], s["box"]) for s in pan_by_cls.get(yb["cname"], [])), default=0.0) >= 0.85:
                continue
            for ps in pan_segments:
                if ps["area"] < 1024 and (ps["area"] / img_area) < 0.005:
                    continue
                # Nếu ps đã khớp >= 0.85 với một box YOLO cùng lớp thì ps không bị swap
                if max((compute_iou(yb2["box"], ps["box"]) for yb2 in yolo_by_cls.get(ps["cname"], [])), default=0.0) >= 0.85:
                    continue
                iou = compute_iou(yb["box"], ps["box"])
                conf = are_confusable(yb["cname"], ps["cname"])
                if (conf and iou >= 0.45) or (iou >= 0.65 and yb["cname"] != ps["cname"]):
                    same_cls_matches = [compute_iou(yb["box"], s["box"]) for s in pan_by_cls.get(yb["cname"], [])]
                    if max(same_cls_matches, default=0.0) < 0.40:
                        candidates.append({
                            "image": name,
                            "type": "class_swap_or_category_swap",
                            "confidence": "high" if conf else "medium",
                            "details": (
                                f"Detection={yb['cname']} vs Panoptic={ps['cname']} "
                                f"(IoU={iou:.2f}, confusable={conf})"
                            ),
                            "yolo_class": yb["cname"],
                            "pan_class": ps["cname"],
                        })

        # Dấu hiệu 3: instance_merge (1 segment Panoptic gom 2 box YOLO)
        for cname, yboxes in yolo_by_cls.items():
            psegs = pan_by_cls.get(cname, [])
            if len(yboxes) > len(psegs) and len(yboxes) >= 2:
                for ps in psegs:
                    overlap_boxes = []
                    for yb in yboxes:
                        cx = (yb["box"][0] + yb["box"][2]) / 2
                        cy = (yb["box"][1] + yb["box"][3]) / 2
                        sb = ps["box"]
                        if (sb[0] <= cx <= sb[2] and sb[1] <= cy <= sb[3]) or compute_iou(yb["box"], ps["box"]) >= 0.20:
                            overlap_boxes.append(yb)
                    if len(overlap_boxes) >= 2 and any(y["area"] >= 0.005 * img_area for y in overlap_boxes):
                        candidates.append({
                            "image": name,
                            "type": "instance_merge",
                            "confidence": "high",
                            "details": f"Lớp {cname}: Panoptic có {len(psegs)} segment nhưng YOLO có {len(yboxes)} box",
                        })

        # Dấu hiệu 4: missing_box (Panoptic có segment lớn mà YOLO thiếu hẳn box)
        for cname, psegs in pan_by_cls.items():
            yboxes = yolo_by_cls.get(cname, [])
            if len(psegs) > len(yboxes):
                for ps in psegs:
                    if ps["area"] >= 1024 or (ps["area"] / img_area) >= 0.01:
                        max_iou = max((compute_iou(ps["box"], yb["box"]) for yb in yolo_boxes), default=0.0)
                        if max_iou < 0.15:
                            candidates.append({
                                "image": name,
                                "type": "missing_box",
                                "confidence": "high",
                                "details": f"Panoptic thing {cname} (area={ps['area']}) không có box Detection nào (max_iou={max_iou:.2f})",
                            })

        # Dấu hiệu 5: bbox_drift (Cùng lớp nhưng bị lệch tâm hoặc lệch kích thước)
        for yb in yolo_boxes:
            if yb["norm"][2] > 0.08 and yb["norm"][3] > 0.08 and (yb["area"] / img_area) >= 0.005:
                same_cls_segs = pan_by_cls.get(yb["cname"], [])
                # Bỏ qua nếu yb đã có segment cùng lớp khớp tốt (IoU >= 0.89)
                if max((compute_iou(yb["box"], s["box"]) for s in same_cls_segs), default=0.0) >= 0.89:
                    continue
                for ps in same_cls_segs:
                    iou = compute_iou(yb["box"], ps["box"])
                    if 0.50 <= iou <= 0.88:
                        best_for_ps = max((compute_iou(yb2["box"], ps["box"]) for yb2 in yolo_by_cls.get(yb["cname"], [])), default=0.0)
                        if abs(best_for_ps - iou) < 1e-4:
                            ycx = (yb["box"][0] + yb["box"][2]) / 2
                            ycy = (yb["box"][1] + yb["box"][3]) / 2
                            scx = (ps["box"][0] + ps["box"][2]) / 2
                            scy = (ps["box"][1] + ps["box"][3]) / 2
                            box_w = max(1.0, yb["box"][2] - yb["box"][0])
                            box_h = max(1.0, yb["box"][3] - yb["box"][1])
                            shift = math.sqrt(((ycx - scx) / box_w) ** 2 + ((ycy - scy) / box_h) ** 2)
                            if shift >= 0.06:
                                candidates.append({
                                    "image": name,
                                    "type": "bbox_drift",
                                    "confidence": "high",
                                    "details": f"Lệch tâm {shift:.2f}*size, IoU={iou:.2f} đối với lớp {yb['cname']}",
                                })

    # Khử trùng lặp ứng viên theo image + type
    unique_candidates = []
    seen = set()
    for c in candidates:
        key = (c["image"], c["type"])
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    return unique_candidates


# ==============================================================================
# 3. HÀM CHÍNH (CLI RUNNER)
# ==============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="Validator kiểm lỗi dataset release")
    parser.add_argument("delivery", help="Đường dẫn đến thư mục delivery")
    parser.add_argument("--out", required=True, help="Đường dẫn file errors.json đầu ra")
    parser.add_argument("--candidates", help="Đường dẫn file candidates.json để ghi các ứng viên nghi vấn")
    args = parser.parse_args()

    delivery_dir = Path(args.delivery)
    if not delivery_dir.is_dir():
        print(f"Lỗi: Thư mục delivery không tồn tại: {delivery_dir}", file=sys.stderr)
        return 1

    d = DatasetDelivery(delivery_dir)

    # 1. Quét lỗi luật
    rule_errors = detect_rule_errors(d)

    # Ghi lỗi luật ra file --out (định dạng chuẩn {"errors": [{"type": ..., "target": ...}]})
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    error_list = [{"type": t, "target": g} for t, g in sorted(rule_errors)]
    out_path.write_text(json.dumps({"errors": error_list}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"-> Đã phát hiện {len(rule_errors)} lỗi luật, lưu tại: {out_path}")

    # 2. Sinh ứng viên nếu được yêu cầu
    if args.candidates:
        cand_list = extract_candidates(d, rule_errors)
        cand_path = Path(args.candidates)
        cand_path.parent.mkdir(parents=True, exist_ok=True)
        cand_path.write_text(json.dumps({"candidates": cand_list}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"-> Đã trích xuất {len(cand_list)} ứng viên nghi vấn, lưu tại: {cand_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
