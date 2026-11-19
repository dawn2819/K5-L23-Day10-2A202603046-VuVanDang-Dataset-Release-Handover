#!/usr/bin/env python3
"""Cong cu xem anh truc quan YOLO <-> Panoptic & ho tro review_log.csv.

Khong can cai thu vien ngoai (chi dung Python 3.10 chuan + trinh duyet web).
Dung duoc cho ca seed luyen tap va de an (40 phut).

Cach dung:
  # 1. Xem tat ca anh (vd: tim anh mat nguoi cho security.md hoac kiem tra wrong_hash):
  python tools/visualizer.py runs/r3007/delivery

  # 2. Review ung vien tu candidates.json va luu thang vao review_log.csv:
  python tools/visualizer.py runs/r3007/delivery --candidates runs/r3007/candidates.json --review runs/r3007/review_log.csv

  # 3. De an:
  python tools/visualizer.py delivery --candidates submission/de_an/candidates.json --review submission/de_an/review_log.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Day 10 Visualizer — YOLO &amp; Panoptic Review</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #111827; color: #f3f4f6; display: flex; height: 100vh; overflow: hidden; }
  #sidebar { width: 320px; background: #1f2937; border-right: 1px solid #374151; display: flex; flex-direction: column; }
  #sidebar header { padding: 12px; border-bottom: 1px solid #374151; }
  #sidebar h2 { margin: 0 0 8px 0; font-size: 15px; color: #60a5fa; }
  .row { display: flex; gap: 6px; margin-bottom: 6px; align-items: center; flex-wrap: wrap; }
  input, select, textarea, button { font: inherit; }
  input[type=text], select, textarea { background: #111827; color: #f9fafb; border: 1px solid #4b5563; border-radius: 5px; padding: 5px 7px; font-size: 13px; }
  button { background: #2563eb; color: #fff; border: none; border-radius: 5px; padding: 6px 10px; font-size: 13px; cursor: pointer; }
  button:hover { background: #1d4ed8; }
  button.sec { background: #374151; }
  button.sec:hover { background: #4b5563; }
  button.ok { background: #059669; }
  button.ok:hover { background: #047857; }
  button.warn { background: #d97706; }
  #list { flex: 1; overflow-y: auto; padding: 6px; }
  .item { padding: 8px; margin-bottom: 4px; border-radius: 6px; background: #111827; border: 1px solid #374151; cursor: pointer; font-size: 12px; }
  .item:hover { border-color: #60a5fa; }
  .item.active { border-color: #3b82f6; background: #1e3a5f; }
  .badge { display: inline-block; padding: 1px 6px; border-radius: 999px; font-size: 11px; font-weight: 600; margin-left: 4px; }
  .b-conf { background: #065f46; color: #a7f3d0; }
  .b-rej { background: #7f1d1d; color: #fecaca; }
  .b-cand { background: #78350f; color: #fde68a; }
  #main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #toolbar { padding: 8px 12px; background: #1f2937; border-bottom: 1px solid #374151; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size: 13px; }
  #workspace { flex: 1; display: flex; overflow: hidden; }
  #canvas-wrap { flex: 1; display: flex; gap: 8px; padding: 10px; overflow: auto; align-items: flex-start; justify-content: center; background: #0b0f19; position: relative; }
  .panel-box { display: flex; flex-direction: column; align-items: center; }
  .panel-title { font-size: 12px; color: #9ca3af; margin-bottom: 4px; }
  canvas { border: 1px solid #374151; background: #000; max-width: 100%; cursor: crosshair; }
  #inspector { width: 360px; background: #1f2937; border-left: 1px solid #374151; display: flex; flex-direction: column; overflow-y: auto; padding: 10px; font-size: 12px; }
  #inspector h3 { margin: 8px 0 4px 0; font-size: 13px; color: #93c5fd; border-bottom: 1px solid #374151; padding-bottom: 3px; }
  .obj-row { padding: 4px 6px; border-radius: 4px; margin-bottom: 3px; background: #111827; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
  .obj-row:hover { background: #374151; }
  .swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; }
  #hover-info { background: #111827; border: 1px solid #374151; border-radius: 6px; padding: 6px 8px; min-height: 44px; color: #e5e7eb; margin-bottom: 8px; }
  #review-box { background: #111827; border: 1px solid #4b5563; border-radius: 6px; padding: 8px; margin-top: 8px; }
  #char-count { font-size: 11px; margin-top: 2px; }
  .ok-txt { color: #34d399; }
  .bad-txt { color: #f87171; }
</style>
</head>
<body>
<div id="sidebar">
  <header>
    <h2>Day 10 Visualizer</h2>
    <div class="row">
      <select id="mode" style="flex:1">
        <option value="candidates">Ung vien (candidates.json)</option>
        <option value="all">Tat ca anh trong lo</option>
        <option value="person">Anh co nguoi (person - security.md)</option>
      </select>
    </div>
    <div class="row">
      <select id="split-half" style="flex:1">
        <option value="all">Tat ca (100%)</option>
        <option value="first">Nua dau — Nguoi A (50%)</option>
        <option value="second">Nua sau — Nguoi B (50%)</option>
      </select>
      <input id="search" type="text" placeholder="Tim ten anh..." style="width:115px">
    </div>
    <div class="row" style="justify-content:space-between; font-size:12px; color:#9ca3af;">
      <span id="stats">0 anh</span>
      <button class="sec" onclick="exportCsv()">Tai review_log.csv</button>
    </div>
  </header>
  <div id="list"></div>
</div>

<div id="main">
  <div id="toolbar">
    <button class="sec" onclick="step(-1)">&larr; Truoc (A)</button>
    <button class="sec" onclick="step(1)">Sau (D) &rarr;</button>
    <strong id="cur-title">Chua chon anh</strong>
    <label><input type="checkbox" id="show-yolo" checked onchange="redraw()"> YOLO Boxes</label>
    <label><input type="checkbox" id="show-mask" checked onchange="redraw()"> Panoptic Mask</label>
    <label><input type="checkbox" id="show-pbox" onchange="redraw()"> Panoptic BBox</label>
    <label><input type="checkbox" id="side-by-side" checked onchange="redraw()"> Song song anh goc</label>
    <label>Mo mask: <input type="range" id="alpha" min="0" max="100" value="42" oninput="redraw()" style="width:70px"></label>
    <label>Zoom:
      <select id="zoom" onchange="redraw()">
        <option value="1">1x</option>
        <option value="1.5" selected>1.5x</option>
        <option value="2">2x</option>
        <option value="3">3x</option>
      </select>
    </label>
    <button class="sec" onclick="resetCrop()">Bo Zoom Crop</button>
  </div>

  <div id="workspace">
    <div id="canvas-wrap">
      <div class="panel-box" id="orig-wrap">
        <div class="panel-title">Anh goc (nhin mat xac nhan vat the)</div>
        <canvas id="cv-orig"></canvas>
      </div>
      <div class="panel-box">
        <div class="panel-title">YOLO (xanh la) + Panoptic Mask (mau + vien trang) — Click vat ben phai de Zoom Crop</div>
        <canvas id="cv-main"></canvas>
      </div>
    </div>

    <div id="inspector">
      <div id="hover-info">Di chuot len anh de xem lop YOLO &amp; Panoptic tai diem do.</div>

      <div id="cand-banner" style="display:none; background:#451a03; border:1px solid #d97706; border-radius:6px; padding:6px 8px; margin-bottom:8px; color:#fde68a;"></div>

      <div id="review-box">
        <h3 style="margin-top:0">Ghi ket qua Review (review_log.csv)</h3>
        <div class="row">
          <label style="width:60px">Loai loi:</label>
          <select id="rev-type" style="flex:1">
            <option value="class_swap">class_swap (Detection sai lop)</option>
            <option value="category_swap">category_swap (Panoptic sai lop)</option>
            <option value="bbox_drift">bbox_drift (Box det bi lech)</option>
            <option value="missing_box">missing_box (Det thieu box)</option>
            <option value="instance_merge">instance_merge (Panoptic gop 2 vat)</option>
          </select>
        </div>
        <div class="row">
          <label style="width:60px">Ket luan:</label>
          <select id="rev-verdict" style="flex:1">
            <option value="confirmed">confirmed (Loi that)</option>
            <option value="rejected">rejected (Lech tu nhien / khong loi)</option>
          </select>
        </div>
        <div>
          <textarea id="rev-note" rows="3" style="width:100%" placeholder="Mo ta cu the mat thay gi tren anh (>= 20 ky tu)... VD: xe tai thung kin mau trang, detection gan nham car con panoptic ghi truck dung" oninput="updateCharCount()"></textarea>
          <div id="char-count" class="bad-txt">0 / 20 ky tu</div>
        </div>
        <div class="row" style="margin-top:6px">
          <button class="ok" style="flex:1" onclick="saveReview()">Luu vao review_log.csv</button>
          <button class="sec" onclick="deleteReview()">Xoa dong</button>
        </div>
        <div id="save-status" style="font-size:11px; color:#93c5fd; margin-top:4px;"></div>
      </div>

      <h3>YOLO Detection Boxes (<span id="yolo-cnt">0</span>)</h3>
      <div id="yolo-list"></div>

      <h3>Panoptic Segments — Things (<span id="pan-cnt">0</span>)</h3>
      <div id="pan-list"></div>
    </div>
  </div>
</div>

<script>
let STATE = {
  allImages: [],
  candidates: [],
  personImages: new Set(),
  reviews: {}, // image -> {image, type, verdict, note}
  filtered: [],
  curIndex: -1,
  detail: null,
  imgEl: null,
  maskData: null,
  maskW: 0,
  maskH: 0,
  crop: null, // {x, y, w, h} in image coords
};

function colorForId(id) {
  const r = (id * 67 + 41) % 210 + 35;
  const g = (id * 131 + 83) % 210 + 35;
  const b = (id * 197 + 19) % 210 + 35;
  return [r, g, b];
}

async function init() {
  const res = await fetch('/api/init');
  const data = await res.json();
  STATE.allImages = data.images;
  STATE.candidates = data.candidates;
  STATE.personImages = new Set(data.person_images);
  STATE.reviews = {};
  for (const r of data.reviews) STATE.reviews[r.image] = r;

  if (STATE.candidates.length === 0) {
    document.getElementById('mode').value = 'all';
  }
  document.getElementById('mode').onchange = rebuildList;
  document.getElementById('split-half').onchange = rebuildList;
  document.getElementById('search').oninput = rebuildList;
  rebuildList();
}

function rebuildList() {
  const mode = document.getElementById('mode').value;
  const half = document.getElementById('split-half').value;
  const q = document.getElementById('search').value.trim().toLowerCase();

  let base = [];
  if (mode === 'candidates') {
    base = STATE.candidates.map(c => ({ image: c.image, cand: c }));
  } else if (mode === 'person') {
    base = STATE.allImages.filter(im => STATE.personImages.has(im)).map(im => ({ image: im, cand: null }));
  } else {
    const candMap = Object.fromEntries(STATE.candidates.map(c => [c.image, c]));
    base = STATE.allImages.map(im => ({ image: im, cand: candMap[im] || null }));
  }

  const mid = Math.ceil(base.length / 2);
  if (half === 'first') base = base.slice(0, mid);
  else if (half === 'second') base = base.slice(mid);

  if (q) base = base.filter(x => x.image.toLowerCase().includes(q) || JSON.stringify(x.cand || '').toLowerCase().includes(q));

  STATE.filtered = base;
  const reviewedCnt = base.filter(x => STATE.reviews[x.image]).length;
  document.getElementById('stats').textContent = `${base.length} anh (da review: ${reviewedCnt})`;

  const listEl = document.getElementById('list');
  listEl.innerHTML = '';
  base.forEach((entry, idx) => {
    const div = document.createElement('div');
    div.className = 'item' + (idx === STATE.curIndex ? ' active' : '');
    const rev = STATE.reviews[entry.image];
    let badges = '';
    if (entry.cand && entry.cand.type) badges += `<span class="badge b-cand">${entry.cand.type}</span>`;
    if (rev) badges += `<span class="badge ${rev.verdict === 'confirmed' ? 'b-conf' : 'b-rej'}">${rev.verdict}</span>`;
    div.innerHTML = `<div><strong>#${idx+1}</strong> ${entry.image}${badges}</div>`;
    if (entry.cand && entry.cand.reason) {
      div.innerHTML += `<div style="color:#9ca3af;margin-top:2px;font-size:11px">${entry.cand.reason}</div>`;
    }
    div.onclick = () => selectIndex(idx);
    listEl.appendChild(div);
  });

  if (base.length > 0 && (STATE.curIndex < 0 || STATE.curIndex >= base.length)) {
    selectIndex(0);
  }
}

function step(delta) {
  if (STATE.filtered.length === 0) return;
  const next = Math.max(0, Math.min(STATE.filtered.length - 1, STATE.curIndex + delta));
  selectIndex(next);
}

async function selectIndex(idx) {
  STATE.curIndex = idx;
  STATE.crop = null;
  document.querySelectorAll('#list .item').forEach((el, i) => el.classList.toggle('active', i === idx));
  const entry = STATE.filtered[idx];
  if (!entry) return;

  document.getElementById('cur-title').textContent = `${entry.image} (#${idx+1}/${STATE.filtered.length})`;
  const res = await fetch(`/api/item/${encodeURIComponent(entry.image)}`);
  STATE.detail = await res.json();

  // Candidate banner
  const banner = document.getElementById('cand-banner');
  if (entry.cand) {
    banner.style.display = 'block';
    banner.innerHTML = `<strong>Ung vien goi y:</strong> ${entry.cand.type || '(chua ro)'}<br>${entry.cand.reason || ''}`;
  } else {
    banner.style.display = 'none';
  }

  // Review form
  const rev = STATE.reviews[entry.image];
  const guessType = rev ? rev.type : (entry.cand && ['class_swap','category_swap','bbox_drift','missing_box','instance_merge'].includes(entry.cand.type) ? entry.cand.type : 'class_swap');
  document.getElementById('rev-type').value = guessType;
  document.getElementById('rev-verdict').value = rev ? rev.verdict : 'confirmed';
  document.getElementById('rev-note').value = rev ? rev.note : '';
  document.getElementById('save-status').textContent = rev ? 'Da co trong review_log.csv' : '';
  updateCharCount();

  // Load image + mask
  const [imgEl, maskImg] = await Promise.all([
    loadImage(STATE.detail.image_url),
    STATE.detail.mask_url ? loadImage(STATE.detail.mask_url).catch(() => null) : Promise.resolve(null),
  ]);
  STATE.imgEl = imgEl;
  if (maskImg) {
    const tmp = document.createElement('canvas');
    tmp.width = maskImg.naturalWidth;
    tmp.height = maskImg.naturalHeight;
    const tctx = tmp.getContext('2d', { willReadFrequently: true });
    tctx.drawImage(maskImg, 0, 0);
    STATE.maskData = tctx.getImageData(0, 0, tmp.width, tmp.height).data;
    STATE.maskW = tmp.width;
    STATE.maskH = tmp.height;
  } else {
    STATE.maskData = null;
  }

  renderObjectLists();
  redraw();
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url + '?t=' + Date.now();
  });
}

function renderObjectLists() {
  const d = STATE.detail;
  const yList = document.getElementById('yolo-list');
  document.getElementById('yolo-cnt').textContent = d.yolo.length;
  yList.innerHTML = '';
  d.yolo.forEach((b, i) => {
    const div = document.createElement('div');
    div.className = 'obj-row';
    div.innerHTML = `<span><span class="swatch" style="background:#22c55e"></span>#${i+1} <strong>${b.class_name}</strong> (id=${b.class_id})</span><span style="color:#9ca3af">${Math.round(b.bw)}x${Math.round(b.bh)}</span>`;
    div.onclick = () => zoomToBox(b.x1, b.y1, b.bw, b.bh);
    yList.appendChild(div);
  });

  const pList = document.getElementById('pan-list');
  const things = d.segments.filter(s => s.isthing);
  document.getElementById('pan-cnt').textContent = things.length;
  pList.innerHTML = '';
  things.forEach(s => {
    const [r, g, b] = colorForId(s.id);
    const div = document.createElement('div');
    div.className = 'obj-row';
    const crowd = s.iscrowd ? ' [crowd]' : '';
    div.innerHTML = `<span><span class="swatch" style="background:rgb(${r},${g},${b})"></span><strong>${s.category_name}</strong>${crowd}</span><span style="color:#9ca3af">area=${s.area}</span>`;
    div.onclick = () => zoomToBox(s.bbox[0], s.bbox[1], s.bbox[2], s.bbox[3]);
    pList.appendChild(div);
  });
}

function zoomToBox(x, y, w, h) {
  if (!STATE.imgEl) return;
  const pad = Math.max(40, Math.max(w, h) * 0.45);
  const iw = STATE.imgEl.naturalWidth, ih = STATE.imgEl.naturalHeight;
  const cx1 = Math.max(0, Math.floor(x - pad));
  const cy1 = Math.max(0, Math.floor(y - pad));
  const cx2 = Math.min(iw, Math.ceil(x + w + pad));
  const cy2 = Math.min(ih, Math.ceil(y + h + pad));
  STATE.crop = { x: cx1, y: cy1, w: Math.max(20, cx2 - cx1), h: Math.max(20, cy2 - cy1) };
  redraw();
}

function resetCrop() {
  STATE.crop = null;
  redraw();
}

function redraw() {
  if (!STATE.imgEl || !STATE.detail) return;
  const img = STATE.imgEl;
  const iw = img.naturalWidth, ih = img.naturalHeight;
  const crop = STATE.crop || { x: 0, y: 0, w: iw, h: ih };
  const zoom = parseFloat(document.getElementById('zoom').value);
  const cw = Math.round(crop.w * zoom);
  const ch = Math.round(crop.h * zoom);

  const side = document.getElementById('side-by-side').checked;
  document.getElementById('orig-wrap').style.display = side ? 'flex' : 'none';
  if (side) {
    const cvO = document.getElementById('cv-orig');
    cvO.width = cw; cvO.height = ch;
    const octx = cvO.getContext('2d');
    octx.drawImage(img, crop.x, crop.y, crop.w, crop.h, 0, 0, cw, ch);
  }

  const cv = document.getElementById('cv-main');
  cv.width = cw; cv.height = ch;
  const ctx = cv.getContext('2d');
  ctx.drawImage(img, crop.x, crop.y, crop.w, crop.h, 0, 0, cw, ch);

  // Draw Panoptic Mask overlay (things only)
  if (document.getElementById('show-mask').checked && STATE.maskData) {
    const alpha = Math.round(parseInt(document.getElementById('alpha').value, 10) * 2.55);
    const thingIds = new Set(STATE.detail.segments.filter(s => s.isthing).map(s => s.id));
    const off = document.createElement('canvas');
    off.width = crop.w; off.height = crop.h;
    const octx = off.getContext('2d');
    const outImg = octx.createImageData(crop.w, crop.h);
    const out = outImg.data;
    const md = STATE.maskData;
    const mw = STATE.maskW;

    for (let dy = 0; dy < crop.h; dy++) {
      const sy = crop.y + dy;
      for (let dx = 0; dx < crop.w; dx++) {
        const sx = crop.x + dx;
        const mi = (sy * mw + sx) * 4;
        const sid = md[mi] + md[mi+1] * 256 + md[mi+2] * 65536;
        if (!thingIds.has(sid)) continue;
        // Edge detection for crisp white border
        let isEdge = false;
        if (dx > 0 && dy > 0 && dx < crop.w - 1 && dy < crop.h - 1) {
          const left = ((sy * mw + (sx - 1)) * 4);
          const up = (((sy - 1) * mw + sx) * 4);
          const idL = md[left] + md[left+1]*256 + md[left+2]*65536;
          const idU = md[up] + md[up+1]*256 + md[up+2]*65536;
          if (idL !== sid || idU !== sid) isEdge = true;
        }
        const oi = (dy * crop.w + dx) * 4;
        if (isEdge) {
          out[oi] = 255; out[oi+1] = 255; out[oi+2] = 255; out[oi+3] = 230;
        } else {
          const [r, g, b] = colorForId(sid);
          out[oi] = r; out[oi+1] = g; out[oi+2] = b; out[oi+3] = alpha;
        }
      }
    }
    octx.putImageData(outImg, 0, 0);
    ctx.drawImage(off, 0, 0, crop.w, crop.h, 0, 0, cw, ch);
  }

  // Draw Panoptic BBoxes (optional)
  if (document.getElementById('show-pbox').checked) {
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.font = 'bold 12px sans-serif';
    for (const s of STATE.detail.segments.filter(x => x.isthing)) {
      const [r, g, b] = colorForId(s.id);
      const x = (s.bbox[0] - crop.x) * zoom;
      const y = (s.bbox[1] - crop.y) * zoom;
      const w = s.bbox[2] * zoom;
      const h = s.bbox[3] * zoom;
      ctx.strokeStyle = `rgb(${r},${g},${b})`;
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = `rgba(${r},${g},${b},0.85)`;
      const label = `P:${s.category_name}`;
      const tw = ctx.measureText(label).width + 6;
      ctx.fillRect(x, Math.max(0, y + h - 16), tw, 16);
      ctx.fillStyle = '#000';
      ctx.fillText(label, x + 3, Math.max(12, y + h - 4));
    }
    ctx.setLineDash([]);
  }

  // Draw YOLO Boxes
  if (document.getElementById('show-yolo').checked) {
    ctx.lineWidth = 2;
    ctx.font = 'bold 12px sans-serif';
    for (const b of STATE.detail.yolo) {
      const x = (b.x1 - crop.x) * zoom;
      const y = (b.y1 - crop.y) * zoom;
      const w = b.bw * zoom;
      const h = b.bh * zoom;
      ctx.strokeStyle = '#22c55e';
      ctx.strokeRect(x, y, w, h);
      const label = `Y:${b.class_name}`;
      const tw = ctx.measureText(label).width + 6;
      ctx.fillStyle = 'rgba(21,128,61,0.9)';
      ctx.fillRect(x, Math.max(0, y - 16), tw, 16);
      ctx.fillStyle = '#fff';
      ctx.fillText(label, x + 3, Math.max(12, y - 4));
    }
  }
}

document.getElementById('cv-main').addEventListener('mousemove', (ev) => {
  if (!STATE.imgEl || !STATE.detail) return;
  const cv = ev.target;
  const rect = cv.getBoundingClientRect();
  const zoom = parseFloat(document.getElementById('zoom').value);
  const crop = STATE.crop || { x: 0, y: 0, w: STATE.imgEl.naturalWidth, h: STATE.imgEl.naturalHeight };
  const ix = Math.floor(crop.x + (ev.clientX - rect.left) * (cv.width / rect.width) / zoom);
  const iy = Math.floor(crop.y + (ev.clientY - rect.top) * (cv.height / rect.height) / zoom);

  let panTxt = 'none';
  if (STATE.maskData && ix >= 0 && iy >= 0 && ix < STATE.maskW && iy < STATE.maskH) {
    const mi = (iy * STATE.maskW + ix) * 4;
    const sid = STATE.maskData[mi] + STATE.maskData[mi+1]*256 + STATE.maskData[mi+2]*65536;
    const seg = STATE.detail.segments.find(s => s.id === sid);
    if (seg) panTxt = `${seg.category_name} (id=${sid}, thing=${seg.isthing}, crowd=${seg.iscrowd})`;
  }
  const yHits = STATE.detail.yolo.filter(b => ix >= b.x1 && ix <= b.x1 + b.bw && iy >= b.y1 && iy <= b.y1 + b.bh).map(b => b.class_name);
  document.getElementById('hover-info').innerHTML =
    `Toa do: (${ix}, ${iy})<br><strong>YOLO:</strong> ${yHits.length ? yHits.join(', ') : '(khong co)'}<br><strong>Panoptic:</strong> ${panTxt}`;
});

function updateCharCount() {
  const n = document.getElementById('rev-note').value.trim().length;
  const el = document.getElementById('char-count');
  el.textContent = `${n} / 20 ky tu ${n >= 20 ? '(Dat chuan H3)' : '(Can >= 20 ky tu!)'}`;
  el.className = n >= 20 ? 'ok-txt' : 'bad-txt';
}

async function saveReview() {
  const entry = STATE.filtered[STATE.curIndex];
  if (!entry) return;
  const payload = {
    image: entry.image,
    type: document.getElementById('rev-type').value,
    verdict: document.getElementById('rev-verdict').value,
    note: document.getElementById('rev-note').value.trim(),
  };
  if (payload.note.length < 20) {
    alert('Ghi chu phai >= 20 ky tu va mo ta cu the mat nhin thay gi tren anh!');
    return;
  }
  const res = await fetch('/api/save_review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const out = await res.json();
  STATE.reviews[payload.image] = payload;
  document.getElementById('save-status').textContent = `Da luu (${out.total} dong trong review_log.csv)`;
  rebuildList();
}

async function deleteReview() {
  const entry = STATE.filtered[STATE.curIndex];
  if (!entry) return;
  await fetch('/api/delete_review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: entry.image }),
  });
  delete STATE.reviews[entry.image];
  document.getElementById('rev-note').value = '';
  document.getElementById('save-status').textContent = 'Da xoa dong review cho anh nay.';
  updateCharCount();
  rebuildList();
}

function exportCsv() {
  window.location.href = '/api/download_review';
}

window.addEventListener('keydown', (e) => {
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
  if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') step(1);
  if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') step(-1);
});

init();
</script>
</body>
</html>
"""


def load_candidates(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("candidates", raw) if isinstance(raw, dict) else raw
    out = []
    for item in items:
        if isinstance(item, str):
            out.append({"image": item, "type": "", "reason": ""})
        elif isinstance(item, dict):
            img = item.get("image") or item.get("target") or item.get("stem") or ""
            tp = item.get("type") or item.get("suspect_type") or item.get("kind") or ""
            reason = item.get("reason") or item.get("detail") or item.get("note") or ""
            if img:
                out.append({"image": str(img), "type": str(tp), "reason": str(reason)})
    return out


def load_reviews(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [
            {
                "image": (r.get("image") or "").strip(),
                "type": (r.get("type") or "").strip(),
                "verdict": (r.get("verdict") or "").strip(),
                "note": (r.get("note") or "").strip(),
            }
            for r in csv.DictReader(f)
            if (r.get("image") or "").strip()
        ]


def save_reviews(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image", "type", "verdict", "note"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: x["image"]):
            w.writerow(r)


def main() -> int:
    ap = argparse.ArgumentParser(description="Visualizer YOLO <-> Panoptic (zero-dependency web UI)")
    ap.add_argument("delivery", help="Thu muc delivery (vd: runs/r3007/delivery hoac delivery)")
    ap.add_argument("--candidates", help="File candidates.json (tuy chon)")
    ap.add_argument("--review", help="File review_log.csv de doc/luu truc tiep (mac dinh canh delivery)")
    ap.add_argument("--port", type=int, default=8765, help="Cong HTTP local (mac dinh 8765)")
    ap.add_argument("--no-browser", action="store_true", help="Khong tu mo trinh duyet")
    args = ap.parse_args()

    delivery = Path(args.delivery).resolve()
    if not delivery.is_dir():
        raise SystemExit(f"Khong tim thay thu muc delivery: {delivery}")

    cand_path = Path(args.candidates).resolve() if args.candidates else None
    review_path = Path(args.review).resolve() if args.review else (delivery.parent / "review_log.csv")

    names80 = [
        ln.split(" ", 1)[1].strip()
        for ln in (delivery / "classes.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    man = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))["items"]
    pan = json.loads((delivery / "panoptic.json").read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in pan["categories"]}
    img_wh = {Path(im["file_name"]).stem: (im["width"], im["height"]) for im in pan["images"]}
    pan_anns = {Path(a["file_name"]).stem: a["segments_info"] for a in pan["annotations"]}

    all_images = sorted(man.keys())
    candidates = load_candidates(cand_path)
    reviews_map = {r["image"]: r for r in load_reviews(review_path)}

    # Tim cac anh co class 'person' (class_id 0) de ho tro security.md
    person_id = names80.index("person") if "person" in names80 else 0
    person_images = []
    for stem in all_images:
        lp = delivery / man[stem]["label"]
        if lp.is_file():
            for ln in lp.read_text(encoding="utf-8").splitlines():
                if ln.strip() and int(float(ln.split()[0])) == person_id:
                    person_images.append(stem)
                    break

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            pass

        def send_json(self, obj, code=HTTPStatus.OK):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/":
                data = HTML_PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if path == "/api/init":
                self.send_json({
                    "images": all_images,
                    "candidates": candidates,
                    "person_images": person_images,
                    "reviews": list(reviews_map.values()),
                })
                return

            if path.startswith("/api/item/"):
                stem = urllib.parse.unquote(path[len("/api/item/"):])
                if stem not in man:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                w, h = img_wh.get(stem, (640, 480))
                yolo_boxes = []
                lp = delivery / man[stem]["label"]
                if lp.is_file():
                    for ln in lp.read_text(encoding="utf-8").splitlines():
                        if not ln.strip():
                            continue
                        parts = ln.split()[:5]
                        cid = int(float(parts[0]))
                        xc, yc, bw, bh = [float(x) for x in parts[1:5]]
                        yolo_boxes.append({
                            "class_id": cid,
                            "class_name": names80[cid] if 0 <= cid < len(names80) else f"INVALID({cid})",
                            "x1": (xc - bw / 2) * w,
                            "y1": (yc - bh / 2) * h,
                            "bw": bw * w,
                            "bh": bh * h,
                        })
                segs = []
                for s in pan_anns.get(stem, []):
                    cinfo = cats.get(s["category_id"], {"name": f"INVALID({s['category_id']})", "isthing": 1})
                    segs.append({
                        "id": s["id"],
                        "category_id": s["category_id"],
                        "category_name": cinfo["name"],
                        "isthing": bool(cinfo.get("isthing", 1)),
                        "area": s["area"],
                        "bbox": s["bbox"],
                        "iscrowd": bool(s.get("iscrowd", 0)),
                    })
                img_rel = man[stem]["image"]
                mask_rel = man[stem]["mask"]
                self.send_json({
                    "image": stem,
                    "width": w,
                    "height": h,
                    "image_url": f"/file/{urllib.parse.quote(img_rel)}",
                    "mask_url": f"/file/{urllib.parse.quote(mask_rel)}" if (delivery / mask_rel).is_file() else None,
                    "yolo": yolo_boxes,
                    "segments": segs,
                })
                return

            if path == "/api/download_review":
                save_reviews(review_path, list(reviews_map.values()))
                data = review_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="review_log.csv"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            if path.startswith("/file/"):
                rel = urllib.parse.unquote(path[len("/file/"):])
                target = (delivery / rel).resolve()
                if not str(target).startswith(str(delivery)) or not target.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                data = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if self.path == "/api/save_review":
                reviews_map[body["image"]] = {
                    "image": body["image"].strip(),
                    "type": body["type"].strip(),
                    "verdict": body["verdict"].strip(),
                    "note": body["note"].strip(),
                }
                save_reviews(review_path, list(reviews_map.values()))
                self.send_json({"ok": True, "total": len(reviews_map)})
                return
            if self.path == "/api/delete_review":
                reviews_map.pop(body.get("image", ""), None)
                save_reviews(review_path, list(reviews_map.values()))
                self.send_json({"ok": True, "total": len(reviews_map)})
                return
            self.send_error(HTTPStatus.NOT_FOUND)

    url = f"http://127.0.0.1:{args.port}/"
    print(f"Visualizer dang chay tai: {url}")
    print(f"  Delivery   : {delivery}")
    print(f"  Candidates : {cand_path or '(khong co - xem toan bo lo)'} ({len(candidates)} ung vien)")
    print(f"  Review CSV : {review_path} ({len(reviews_map)} dong hien co)")
    print("Nhan Ctrl+C de dung server.")
    if not args.no_browser:
        webbrowser.open(url)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDa dung Visualizer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
