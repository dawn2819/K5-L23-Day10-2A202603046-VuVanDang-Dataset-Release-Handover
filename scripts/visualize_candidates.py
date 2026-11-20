#!/usr/bin/env python3
"""Công cụ trực quan hóa ứng viên nghi vấn (Visualizer Helper).

Đọc candidates.json và thư mục delivery, tạo file HTML trực quan review_viewer.html
vẽ bounding box YOLO (màu xanh lá) và Panoptic mask/box (màu tím/xanh dương)
giúp con người mở trình duyệt là thấy ngay dị thường để chốt confirmed / rejected.

Sử dụng:
  python scripts/visualize_candidates.py --run runs/r3007 [--out runs/r3007/review_viewer.html]
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def load_dataset(delivery_dir: Path):
    classes_path = delivery_dir / "classes.txt"
    names80 = []
    if classes_path.is_file():
        for line in classes_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                parts = line.strip().split(" ", 1)
                names80.append(parts[1].strip() if len(parts) == 2 else parts[0].strip())

    panoptic_path = delivery_dir / "panoptic.json"
    cat_by_id = {}
    pan_images = {}
    pan_anns = {}
    if panoptic_path.is_file():
        pdoc = json.loads(panoptic_path.read_text(encoding="utf-8"))
        for cat in pdoc.get("categories", []):
            cat_by_id[cat["id"]] = cat
        for im in pdoc.get("images", []):
            stem = Path(im["file_name"]).stem
            pan_images[stem] = im
            pan_images[im["id"]] = im
        for ann in pdoc.get("annotations", []):
            pan_anns[ann["image_id"]] = ann

    manifest_path = delivery_dir / "manifest.json"
    manifest_items = {}
    if manifest_path.is_file():
        manifest_items = json.loads(manifest_path.read_text(encoding="utf-8")).get("items", {})

    return names80, cat_by_id, pan_images, pan_anns, manifest_items


def render_candidate_image(delivery_dir: Path, img_name: str, names80, cat_by_id, pan_images, pan_anns, manifest_items) -> str:
    man_item = manifest_items.get(img_name)
    if not man_item:
        return ""
    img_path = delivery_dir / man_item["image"]
    if not img_path.is_file():
        return ""

    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)

    # 1. Vẽ Panoptic segments (màu cyan / tím nhạt)
    im_info = pan_images.get(img_name)
    if im_info:
        ann = pan_anns.get(im_info["id"])
        if ann:
            for seg in ann.get("segments_info", []):
                cat = cat_by_id.get(seg["category_id"])
                if cat and cat.get("isthing") and not seg.get("iscrowd"):
                    sb = seg["bbox"]
                    x1, y1, x2, y2 = sb[0], sb[1], sb[0] + sb[2], sb[1] + sb[3]
                    draw.rectangle([x1, y1, x2, y2], outline="#00e5ff", width=2)
                    cname = cat["name"]
                    draw.text((x1 + 2, y1 + 2), f"Pan: {cname}", fill="#00e5ff")

    # 2. Vẽ YOLO Detection boxes (màu xanh lá tươi)
    lbl_path = delivery_dir / man_item["label"]
    if lbl_path.is_file():
        for line in lbl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cid = int(float(parts[0]))
            cname = names80[cid] if 0 <= cid < len(names80) else str(cid)
            x, y, w, h = map(float, parts[1:5])
            x1 = (x - w / 2) * W
            y1 = (y - h / 2) * H
            x2 = (x + w / 2) * W
            y2 = (y + h / 2) * H
            draw.rectangle([x1, y1, x2, y2], outline="#00ff66", width=2)
            draw.text((x1 + 2, max(0, y1 - 12)), f"Det: {cname}", fill="#00ff66")

    # Encode sang base64 để nhúng thẳng vào HTML
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Tạo HTML xem ứng viên review")
    parser.add_argument("--run", help="Thư mục run (ví dụ: runs/r3007)")
    parser.add_argument("--delivery", help="Thư mục delivery (ví dụ: delivery)")
    parser.add_argument("--candidates", help="File candidates.json")
    parser.add_argument("--out", help="Đường dẫn file HTML đầu ra")
    args = parser.parse_args()

    if args.delivery:
        delivery_dir = Path(args.delivery)
        cand_path = Path(args.candidates) if args.candidates else delivery_dir.parent / "candidates.json"
        out_file = Path(args.out) if args.out else Path("review_viewer.html")
        run_name = delivery_dir.name
    elif args.run:
        run_dir = Path(args.run)
        delivery_dir = run_dir / "delivery" if (run_dir / "delivery").is_dir() else run_dir
        cand_path = Path(args.candidates) if args.candidates else run_dir / "candidates.json"
        out_file = Path(args.out) if args.out else run_dir / "review_viewer.html"
        run_name = run_dir.name
    else:
        print("Lỗi: Cần truyền --run hoặc --delivery")
        return 1

    if not cand_path.is_file():
        print(f"Lỗi: Không tìm thấy {cand_path}")
        return 1

    cands_data = json.loads(cand_path.read_text(encoding="utf-8"))
    candidates = cands_data.get("candidates", [])

    names80, cat_by_id, pan_images, pan_anns, manifest_items = load_dataset(delivery_dir)

    cards_html = []
    for idx, c in enumerate(candidates, 1):
        img_name = c["image"]
        b64_img = render_candidate_image(delivery_dir, img_name, names80, cat_by_id, pan_images, pan_anns, manifest_items)

        cards_html.append(f"""
        <div class="card" id="card-{idx}">
            <div class="card-header">
                <h3>#{idx}. Ảnh: <code>{img_name}</code> — Nghi vấn: <span class="badge">{c.get('type')}</span></h3>
                <p><strong>Chi tiết phát hiện:</strong> {c.get('details', '')}</p>
            </div>
            <div class="card-body">
                <div class="img-container">
                    <img src="data:image/jpeg;base64,{b64_img}" alt="{img_name}">
                </div>
                <div class="legend">
                    <span style="color: #00ff66;">■ Detection (YOLO)</span> &nbsp;&nbsp;|&nbsp;&nbsp;
                    <span style="color: #00e5ff;">■ Panoptic (Segmentation)</span>
                </div>
            </div>
        </div>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Visual Review Candidates — {run_name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
        h1 {{ text-align: center; color: #38bdf8; margin-bottom: 5px; }}
        .subtitle {{ text-align: center; color: #94a3b8; margin-bottom: 25px; }}
        .card {{ background: #1e293b; border-radius: 12px; margin-bottom: 25px; border: 1px solid #334155; overflow: hidden; }}
        .card-header {{ padding: 15px 20px; background: #243248; border-bottom: 1px solid #334155; }}
        .card-header h3 {{ margin: 0 0 8px 0; font-size: 1.2rem; }}
        .badge {{ background: #f59e0b; color: #000; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: bold; }}
        .card-body {{ padding: 20px; text-align: center; }}
        .img-container {{ max-width: 100%; overflow: auto; display: inline-block; background: #000; border-radius: 8px; padding: 4px; }}
        .img-container img {{ max-width: 100%; height: auto; display: block; }}
        .legend {{ margin-top: 10px; font-weight: 500; font-size: 0.95rem; }}
        code {{ background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #f43f5e; }}
    </style>
</head>
<body>
    <h1>🔍 Công Cụ Hỗ Trợ Review Ảnh Nghi Vấn</h1>
    <div class="subtitle">Tìm thấy {len(candidates)} ứng viên nghi vấn cần mắt người xác nhận cho {run_name}</div>
    <div class="container">
        {''.join(cards_html)}
    </div>
</body>
</html>
"""
    out_file.write_text(html_content, encoding="utf-8")
    print(f"-> Đã tạo file HTML xem ảnh review tại: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
