#!/usr/bin/env python3
"""
Generate 1915區.geojson by splitting 支廳 polygons along white boundary lines.
Also produces label_tool_2.html for verifying auto-matched 區 names.
"""

import xml.etree.ElementTree as ET, re, json
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, Point
from shapely.ops import split, unary_union
from shapely.validation import make_valid

SVG_FILE = "/home/srwang/testenv/20260403/1915_Taihoku_Cho.svg"
JIATING_GEOJSON = "/home/srwang/testenv/20260403/1915支廳.geojson"
OUTPUT_GEOJSON  = "/home/srwang/testenv/20260403/1915區.geojson"
OUTPUT_HTML     = "/home/srwang/testenv/20260403/label_tool_2.html"

# Same 2-point alignment as 支廳 geojson
NTPC_E_LON, NTPC_E_LAT =  122.0076, 25.008286
NTPC_N_LON, NTPC_N_LAT =  121.577008, 25.298403

SVG_NS      = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"

# ── SVG parsing helpers ────────────────────────────────────────────────────────
def parse_translate(t):
    m = re.search(r'translate\(\s*([-\d.e+]+)\s*,\s*([-\d.e+]+)\s*\)', t or '')
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)

def tokenize(d):
    return re.findall(r'[MmLlHhVvCcZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', d)

def bez(p0, p1, p2, p3, steps=12):
    return [((1-t)**3*p0[0]+3*(1-t)**2*t*p1[0]+3*(1-t)*t**2*p2[0]+t**3*p3[0],
             (1-t)**3*p0[1]+3*(1-t)**2*t*p1[1]+3*(1-t)*t**2*p2[1]+t**3*p3[1])
            for t in (i/steps for i in range(1, steps+1))]

def parse_path_segments(d, tx=0.0, ty=0.0):
    """Return list of segment-lists (each segment is a list of (x,y)).
    Starts a new segment on each M/m command."""
    tokens = tokenize(d); n = len(tokens); i = 0
    cmd = None; cx = cy = sx = sy = 0.0
    segments = []; cur = []
    def nf():
        nonlocal i; v = float(tokens[i]); i += 1; return v
    def push():
        if len(cur) >= 2: segments.append(list(cur))
    while i < n:
        tok = tokens[i]
        if re.match(r'^[MmLlHhVvCcZz]$', tok): cmd = tok; i += 1
        if cmd == 'M':
            push(); cur = []; cx=nf(); cy=nf(); sx,sy=cx,cy; cur.append((cx+tx,cy+ty)); cmd='L'
        elif cmd == 'm':
            push(); cur = []; cx+=nf(); cy+=nf(); sx,sy=cx,cy; cur.append((cx+tx,cy+ty)); cmd='l'
        elif cmd == 'L': cx=nf(); cy=nf(); cur.append((cx+tx,cy+ty))
        elif cmd == 'l': cx+=nf(); cy+=nf(); cur.append((cx+tx,cy+ty))
        elif cmd == 'H': cx=nf(); cur.append((cx+tx,cy+ty))
        elif cmd == 'h': cx+=nf(); cur.append((cx+tx,cy+ty))
        elif cmd == 'V': cy=nf(); cur.append((cx+tx,cy+ty))
        elif cmd == 'v': cy+=nf(); cur.append((cx+tx,cy+ty))
        elif cmd == 'C':
            x1,y1=nf(),nf(); x2,y2=nf(),nf(); x3,y3=nf(),nf()
            for p in bez((cx,cy),(x1,y1),(x2,y2),(x3,y3)): cur.append((p[0]+tx,p[1]+ty))
            cx,cy=x3,y3
        elif cmd == 'c':
            dx1,dy1=nf(),nf(); dx2,dy2=nf(),nf(); dx3,dy3=nf(),nf()
            for p in bez((cx,cy),(cx+dx1,cy+dy1),(cx+dx2,cy+dy2),(cx+dx3,cy+dy3)):
                cur.append((p[0]+tx, p[1]+ty))
            cx+=dx3; cy+=dy3
        elif cmd in ('Z','z'):
            # close: add first point and push
            if cur: cur.append(cur[0])
            push(); cur=[]; cx,cy=sx,sy
        else: i += 1
    push()
    return segments

def parse_polygon_rings(d, tx=0.0, ty=0.0):
    segs = parse_path_segments(d, tx, ty)
    rings = []
    for seg in segs:
        if len(seg) >= 3:
            if seg[0] != seg[-1]: seg = seg + [seg[0]]
            rings.append(seg)
    return rings

# ── Parse SVG ──────────────────────────────────────────────────────────────────
tree = ET.parse(SVG_FILE)
root = tree.getroot()

fill_paths   = []  # (id, fill, rings_in_svg_coords)
stroke_paths = []  # list of segment lists (SVG coords)

for layer in root.iter(f'{{{SVG_NS}}}g'):
    if layer.get(f'{{{INKSCAPE_NS}}}label') != 'Layer 1': continue
    ltx, lty = parse_translate(layer.get('transform',''))
    for child in layer:
        if child.tag == f'{{{SVG_NS}}}g':
            gtx, gty = parse_translate(child.get('transform','')); paths = list(child)
        elif child.tag == f'{{{SVG_NS}}}path':
            gtx, gty = 0.0, 0.0; paths = [child]
        else: continue
        for path in paths:
            if path.tag != f'{{{SVG_NS}}}path': continue
            style = path.get('style',''); d = path.get('d','')
            if not d: continue
            pid = path.get('id','')
            if 'fill:none' in style and 'stroke:#ffffff' in style:
                segs = parse_path_segments(d, ltx+gtx, lty+gty)
                stroke_paths.extend(segs)
            elif 'fill:none' not in style and re.search(r'fill:#', style):
                fill_m = re.search(r'fill:(#[0-9a-fA-F]+)', style)
                fill_color = fill_m.group(1) if fill_m else '#cccccc'
                rings = parse_polygon_rings(d, ltx+gtx, lty+gty)
                if rings: fill_paths.append((pid, fill_color, rings))

print(f"Fill paths: {len(fill_paths)}, Stroke paths: {len(stroke_paths)}")

# ── Load 支廳 name map ─────────────────────────────────────────────────────────
with open(JIATING_GEOJSON) as f: jiating = json.load(f)
id_to_name = {feat['properties']['id']: feat['properties']['name'] for feat in jiating['features']}

# ── Build Shapely geometries ───────────────────────────────────────────────────
# 支廳 polygons in SVG pixel coords
shapely_jiating = []
for pid, fill, rings in fill_paths:
    exterior = rings[0]
    holes    = rings[1:]
    try:
        poly = Polygon(exterior, holes)
        poly = make_valid(poly)
        if poly.geom_type not in ('Polygon','MultiPolygon'):
            polys = [g for g in poly.geoms if g.geom_type in ('Polygon','MultiPolygon')]
            poly = unary_union(polys) if polys else None
        if poly is None or poly.is_empty: continue
        if poly.geom_type == 'MultiPolygon':
            poly = max(poly.geoms, key=lambda g: g.area)
        shapely_jiating.append({'id': pid, 'fill': fill, 'name': id_to_name.get(pid,''), 'poly': poly})
    except Exception as e:
        print(f"  Skip invalid polygon {pid}: {e}")

# White boundary lines
def extend_line(pts, amount=5.0):
    """Extend line at both ends by `amount` pixels."""
    if len(pts) < 2: return pts
    x0,y0 = pts[0]; x1,y1 = pts[1]
    d = ((x1-x0)**2+(y1-y0)**2)**0.5
    if d < 1e-9: return pts
    dx,dy = (x0-x1)/d*amount, (y0-y1)/d*amount
    start = (x0+dx, y0+dy)
    x0,y0 = pts[-1]; x1,y1 = pts[-2]
    d = ((x1-x0)**2+(y1-y0)**2)**0.5
    if d < 1e-9: return pts
    dx,dy = (x0-x1)/d*amount, (y0-y1)/d*amount
    end = (x0+dx, y0+dy)
    return [start] + list(pts[1:-1]) + [end]

white_lines = []
for seg in stroke_paths:
    if len(seg) >= 2:
        ext = extend_line(seg, 8.0)
        white_lines.append(LineString(ext))

print(f"White lines: {len(white_lines)}")

# ── Split 支廳 polygons ────────────────────────────────────────────────────────
def split_by_lines(polygon, lines):
    parts = [polygon]
    for line in lines:
        new_parts = []
        for part in parts:
            try:
                if line.crosses(part) or (line.intersects(part) and line.difference(part).is_empty == False):
                    result = split(part, line)
                    new_parts.extend([g for g in result.geoms])
                else:
                    new_parts.append(part)
            except Exception:
                new_parts.append(part)
        parts = new_parts
    return parts

all_districts = []
total_split = 0
for jiating_info in shapely_jiating:
    poly = jiating_info['poly']
    # Find lines that are relevant to this polygon (intersect its interior)
    relevant = [l for l in white_lines if l.intersects(poly) and not poly.exterior.contains(l)]
    pieces = split_by_lines(poly, relevant)
    # Filter tiny fragments (< 1% of original area)
    min_area = poly.area * 0.005
    pieces = [p for p in pieces if p.area > min_area and p.is_valid and not p.is_empty]
    total_split += len(pieces)
    for piece in pieces:
        all_districts.append({
            'parent_id':   jiating_info['id'],
            'parent_name': jiating_info['name'],
            'parent_fill': jiating_info['fill'],
            'poly':        piece,
            'name':        '',
        })

print(f"After split: {total_split} district polygons")

# ── Extract & group text labels ────────────────────────────────────────────────
raw_labels = []
for t in root.iter(f'{{{SVG_NS}}}text'):
    x = float(t.get('x', 0)); y = float(t.get('y', 0))
    style = t.get('style','')
    if 'fill:#ff0000' in style: continue   # skip red 支廳 labels
    content = ''.join(t.itertext()).strip()
    if not content or y > 700: continue    # skip title/legend at bottom
    if content in ('1915年臺北廳行政區劃圖','（不含蕃地）'): continue
    raw_labels.append({'x': x, 'y': y, 'text': content})

# Special replacements for single-letter markers
AB_MAP = {'a': '艋舺區', 'b': '大稻埕區'}
for lab in raw_labels:
    if lab['text'] in AB_MAP:
        lab['text'] = AB_MAP[lab['text']]

# Group single CJK characters into vertical-text clusters
# Use connected-components with 40px threshold to avoid merging nearby labels
def is_single_cjk(s):
    return len(s) == 1 and '\u4e00' <= s <= '\u9fff'

single_char = [l for l in raw_labels if is_single_cjk(l['text'])]
multi_char  = [l for l in raw_labels if not is_single_cjk(l['text'])]

CLUSTER_DIST = 40  # px — tight enough to separate adjacent vertical labels

n_sc = len(single_char)
adj = [[] for _ in range(n_sc)]
for i in range(n_sc):
    for j in range(i+1, n_sc):
        a, b = single_char[i], single_char[j]
        if (a['x']-b['x'])**2 + (a['y']-b['y'])**2 < CLUSTER_DIST**2:
            adj[i].append(j); adj[j].append(i)

visited = [False]*n_sc
clusters = []
for start in range(n_sc):
    if visited[start]: continue
    stack = [start]; group = []
    while stack:
        node = stack.pop()
        if visited[node]: continue
        visited[node] = True; group.append(node)
        stack.extend(adj[node])
    members = sorted([single_char[k] for k in group], key=lambda l: l['y'])
    cx = sum(m['x'] for m in members) / len(members)
    cy = sum(m['y'] for m in members) / len(members)
    text = ''.join(m['text'] for m in members)
    clusters.append({'x': cx, 'y': cy, 'text': text})

all_labels = multi_char + clusters
print(f"Text labels after grouping: {len(all_labels)}")

# ── Auto-match labels to district polygons ─────────────────────────────────────
for lab in all_labels:
    pt = Point(lab['x'], lab['y'])
    for d in all_districts:
        if d['poly'].contains(pt):
            d['name'] = lab['text']
            break

matched   = sum(1 for d in all_districts if d['name'])
unmatched = sum(1 for d in all_districts if not d['name'])
print(f"Matched: {matched}, Unmatched: {unmatched}")

# ── Coordinate transform (SVG px → WGS84) ─────────────────────────────────────
all_pts_svg = []
for d in all_districts:
    coords = list(d['poly'].exterior.coords)
    all_pts_svg.extend(coords)

mnx = min(p[0] for p in all_pts_svg)
mxx = max(p[0] for p in all_pts_svg)
mny = min(p[1] for p in all_pts_svg)
mxy = max(p[1] for p in all_pts_svg)

# East pt: max x in SVG → (NTPC_E_LON, NTPC_E_LAT)
# North pt: min y in SVG → (NTPC_N_LON, NTPC_N_LAT)
east_px  = max(all_pts_svg, key=lambda p: p[0])
north_px = min(all_pts_svg, key=lambda p: p[1])
ex, ey = east_px; nx, ny = north_px

scaleX = (NTPC_E_LON - NTPC_N_LON) / (ex - nx)
tx_geo = NTPC_E_LON - scaleX * ex
scaleY = (NTPC_N_LAT - NTPC_E_LAT) / (ey - ny)
ty_geo = NTPC_E_LAT + scaleY * ey

def to_geo(px, py):
    return [round(scaleX*px + tx_geo, 6), round(-scaleY*py + ty_geo, 6)]

def poly_to_geo_coords(shapely_poly):
    coords = [to_geo(x, y) for x, y in shapely_poly.exterior.coords]
    holes  = [[to_geo(x,y) for x,y in ring.coords] for ring in shapely_poly.interiors]
    return [coords] + holes

# ── Build GeoJSON features ─────────────────────────────────────────────────────
features = []
for idx, d in enumerate(all_districts):
    if isinstance(d['poly'], (Polygon,)):
        polys = [d['poly']]
    else:
        polys = list(d['poly'].geoms)
    for poly in polys:
        if not poly.is_valid or poly.is_empty or poly.area < 1: continue
        features.append({
            "type": "Feature",
            "properties": {
                "id":          f"dist_{idx}",
                "name":        d['name'],
                "parent_id":   d['parent_id'],
                "parent_name": d['parent_name'],
                "fill":        d['parent_fill'],
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": poly_to_geo_coords(poly)
            }
        })

print(f"GeoJSON features: {len(features)}")
geojson = {
    "type": "FeatureCollection",
    "name": "1915區",
    "crs": {"type":"name","properties":{"name":"urn:ogc:def:crs:OGC:1.3:CRS84"}},
    "features": features
}
with open(OUTPUT_GEOJSON, 'w', encoding='utf-8') as f:
    json.dump(geojson, f, ensure_ascii=False, separators=(',',':'))
print(f"Saved → {OUTPUT_GEOJSON}")

# ── Build canvas display data (SVG pixel coords, normalised 0–1) ───────────────
svg_w, svg_h = 1200, 800
canvas_feats = []
for idx, d in enumerate(all_districts):
    poly = d['poly']
    if not poly.is_valid or poly.is_empty: continue
    # exterior ring normalised coords
    ring = [[round(x/svg_w, 5), round(y/svg_h, 5)] for x,y in poly.exterior.coords]
    centroid = poly.centroid
    canvas_feats.append({
        'id':          f"dist_{idx}",
        'name':        d['name'],
        'parent_name': d['parent_name'],
        'fill':        d['parent_fill'],
        'ring':        ring,
        'cx':          round(centroid.x/svg_w, 5),
        'cy':          round(centroid.y/svg_h, 5),
    })

# ── Generate HTML label tool ───────────────────────────────────────────────────
canvas_data_js = json.dumps(canvas_feats, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>1915 台北廳 — 區名確認工具</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:sans-serif;background:#f0f0f0;height:100vh;display:flex;flex-direction:column}}
h1{{padding:8px 16px;font-size:15px;background:#2c3e50;color:#fff;flex-shrink:0}}
.main{{display:flex;flex:1;overflow:hidden;gap:8px;padding:8px}}

.panel-map{{display:flex;flex-direction:column;flex:3;background:#fff;border-radius:6px;
            overflow:hidden;box-shadow:0 1px 4px #0002}}
.panel-map h2{{padding:6px 12px;font-size:12px;background:#ecf0f1;border-bottom:1px solid #ddd}}
#canvas-wrap{{flex:1;position:relative;overflow:hidden}}
#canvas-wrap img.svg-bg{{position:absolute;top:0;left:0;width:100%;height:100%;
                          object-fit:fill;opacity:0.35;pointer-events:none}}
canvas{{position:absolute;top:0;left:0;cursor:crosshair}}

.panel-list{{display:flex;flex-direction:column;flex:1;min-width:260px;max-width:320px;
              background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px #0002}}
.panel-list h2{{padding:6px 12px;font-size:12px;background:#ecf0f1;border-bottom:1px solid #ddd;flex-shrink:0}}
.list-stats{{padding:4px 12px;font-size:11px;color:#888;flex-shrink:0;border-bottom:1px solid #eee}}
#poly-list{{flex:1;overflow-y:auto;padding:6px}}
.group-header{{font-size:11px;font-weight:bold;color:#555;padding:6px 4px 2px;
               border-top:1px solid #eee;margin-top:4px}}
.poly-row{{display:flex;align-items:center;gap:5px;padding:4px 5px;border-radius:4px;
           cursor:pointer;border:2px solid transparent;margin-bottom:2px;transition:background .1s}}
.poly-row:hover{{background:#f5f5f5}}
.poly-row.selected{{border-color:#e74c3c;background:#fdf3f3}}
.swatch{{width:16px;height:16px;border-radius:2px;border:1px solid #aaa;flex-shrink:0}}
.poly-row input{{flex:1;font-size:12px;padding:2px 5px;border:1px solid #ccc;border-radius:3px}}
.poly-row input.changed{{border-color:#e67e22;background:#fffbf0}}
.poly-row input.empty{{border-color:#e74c3c;background:#fff5f5}}

.bottom{{display:flex;gap:8px;padding:0 8px 8px;flex-shrink:0;align-items:flex-start}}
.ref-wrap{{flex:1;background:#fff;border-radius:6px;box-shadow:0 1px 4px #0002;
           overflow:auto;max-height:160px;padding:6px}}
.ref-wrap img{{max-width:100%;height:auto;display:block}}
.export-wrap{{flex:0 0 300px;background:#fff;border-radius:6px;box-shadow:0 1px 4px #0002;padding:10px}}
.export-wrap h2{{font-size:13px;margin-bottom:6px;color:#555}}
#export-btn{{background:#27ae60;color:#fff;border:none;padding:7px 0;border-radius:4px;
             cursor:pointer;font-size:13px;width:100%;margin-bottom:5px}}
#export-btn:hover{{background:#219a52}}
#output{{width:100%;height:80px;font-size:10px;font-family:monospace;
         border:1px solid #ccc;border-radius:3px;padding:4px;resize:none}}
#copy-btn{{background:#2980b9;color:#fff;border:none;padding:4px 12px;
           border-radius:3px;cursor:pointer;font-size:12px;margin-top:3px}}
</style>
</head>
<body>
<h1>1915 台北廳行政區劃 — 區名確認工具（共 {len(canvas_feats)} 個區）</h1>
<div class="main">
  <div class="panel-map">
    <h2>點擊區域選取（灰色底圖為原 SVG 參考）</h2>
    <div id="canvas-wrap">
      <img class="svg-bg" src="1915_Taihoku_Cho.svg" alt="">
      <canvas id="map"></canvas>
    </div>
  </div>
  <div class="panel-list">
    <h2>區名確認（橘框＝已修改，紅框＝尚未命名）</h2>
    <div class="list-stats" id="stats"></div>
    <div id="poly-list"></div>
  </div>
</div>
<div class="bottom">
  <div class="ref-wrap">
    <img src="1915_Taihoku_Cho.svg" alt="原始 SVG 參考圖">
  </div>
  <div class="export-wrap">
    <h2>匯出結果 JSON</h2>
    <button id="export-btn">產生 JSON 對應表</button>
    <textarea id="output" readonly placeholder="按上方按鈕產生..."></textarea>
    <button id="copy-btn">複製到剪貼簿</button>
  </div>
</div>
<script>
const DATA = {canvas_data_js};
const canvas = document.getElementById('map');
const ctx    = canvas.getContext('2d');
const wrap   = document.getElementById('canvas-wrap');
let selectedIdx = null;
const editedNames = {{}};

// ── Init list ─────────────────────────────────────────────────────────────────
const listEl = document.getElementById('poly-list');
let lastParent = null;
DATA.forEach((d, idx) => {{
  if (d.parent_name !== lastParent) {{
    lastParent = d.parent_name;
    const hdr = document.createElement('div');
    hdr.className = 'group-header';
    hdr.textContent = d.parent_name || '（未分類）';
    hdr.style.color = d.fill;
    listEl.appendChild(hdr);
  }}
  const row = document.createElement('div');
  row.className = 'poly-row'; row.dataset.idx = idx;
  const inp = document.createElement('input');
  inp.type = 'text'; inp.value = d.name;
  inp.className = d.name ? '' : 'empty';
  inp.addEventListener('input', () => {{
    editedNames[idx] = inp.value;
    inp.className = inp.value === d.name ? '' : (inp.value ? 'changed' : 'empty');
    updateStats(); draw();
  }});
  row.innerHTML = `<div class="swatch" style="background:${{d.fill}}"></div>`;
  row.appendChild(inp);
  row.addEventListener('click', e => {{ if (e.target === inp) return; selectPoly(idx); }});
  listEl.appendChild(row);
}});

function getName(idx) {{
  return idx in editedNames ? editedNames[idx] : DATA[idx].name;
}}
function updateStats() {{
  const empty = DATA.filter((_,i) => !getName(i)).length;
  document.getElementById('stats').textContent =
    `已命名 ${{DATA.length - empty}} / ${{DATA.length}}，未命名 ${{empty}}`;
}}
updateStats();

// ── Canvas ────────────────────────────────────────────────────────────────────
function resize() {{
  canvas.width  = wrap.clientWidth;
  canvas.height = wrap.clientHeight;
  draw();
}}
function toXY(nx, ny) {{
  return [nx * canvas.width, ny * canvas.height];
}}
function draw() {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  DATA.forEach((d, idx) => {{
    ctx.beginPath();
    const [x0,y0] = toXY(d.ring[0][0], d.ring[0][1]);
    ctx.moveTo(x0, y0);
    for (let i=1;i<d.ring.length;i++) {{
      const [x,y]=toXY(d.ring[i][0],d.ring[i][1]); ctx.lineTo(x,y);
    }}
    ctx.closePath();
    // Fill with semi-transparent parent colour
    const hex = d.fill;
    const r=parseInt(hex.slice(1,3),16), g=parseInt(hex.slice(3,5),16), b=parseInt(hex.slice(5,7),16);
    const isSel = idx === selectedIdx;
    ctx.fillStyle = `rgba(${{r}},${{g}},${{b}},${{isSel ? 0.85 : 0.55}})`;
    ctx.fill();
    ctx.strokeStyle = isSel ? '#e74c3c' : 'rgba(80,80,80,0.6)';
    ctx.lineWidth   = isSel ? 2 : 0.6;
    ctx.stroke();
    // Label
    const name = getName(idx);
    if (name) {{
      const [cx,cy] = toXY(d.cx, d.cy);
      ctx.font = '9px sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillStyle = '#111';
      ctx.fillText(name.length > 5 ? name.slice(0,5)+'…' : name, cx, cy);
    }}
  }});
}}
function selectPoly(idx) {{
  selectedIdx = idx;
  document.querySelectorAll('.poly-row').forEach((r,i) => {{
    r.classList.toggle('selected', i === idx);
    if (i === idx) r.scrollIntoView({{block:'nearest'}});
  }});
  draw();
}}
function hitTest(mx, my) {{
  for (let idx=DATA.length-1;idx>=0;idx--) {{
    const ring=DATA[idx].ring; let inside=false;
    for (let i=0,j=ring.length-1;i<ring.length;j=i++) {{
      const [xi,yi]=toXY(ring[i][0],ring[i][1]);
      const [xj,yj]=toXY(ring[j][0],ring[j][1]);
      if (((yi>my)!==(yj>my)) && (mx<(xj-xi)*(my-yi)/(yj-yi)+xi)) inside=!inside;
    }}
    if (inside) return idx;
  }}
  return null;
}}
canvas.addEventListener('click', e => {{
  const r=canvas.getBoundingClientRect(), idx=hitTest(e.clientX-r.left, e.clientY-r.top);
  if (idx!==null) selectPoly(idx);
}});
canvas.addEventListener('mousemove', e => {{
  const r=canvas.getBoundingClientRect(), idx=hitTest(e.clientX-r.left, e.clientY-r.top);
  canvas.style.cursor = idx!==null ? 'pointer' : 'crosshair';
}});

// ── Export ────────────────────────────────────────────────────────────────────
document.getElementById('export-btn').addEventListener('click', () => {{
  const result = {{}};
  DATA.forEach((d,i) => {{
    result[d.id] = {{name: getName(i), parent_name: d.parent_name}};
  }});
  document.getElementById('output').value = JSON.stringify(result, null, 2);
}});
document.getElementById('copy-btn').addEventListener('click', () => {{
  const ta = document.getElementById('output');
  ta.select(); document.execCommand('copy');
}});

new ResizeObserver(resize).observe(wrap);
resize();
</script>
</body>
</html>"""

with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html)
print(f"Saved → {OUTPUT_HTML}  ({len(html)//1024} KB)")
