#!/usr/bin/env python3
"""
Convert 1915 Taihoku Cho SVG to GeoJSON.
Two-point alignment: SVG extreme-East → NTPC extreme-East, SVG extreme-North → NTPC extreme-North.
Non-uniform scale + translation (no rotation).
"""

import xml.etree.ElementTree as ET
import re, json

SVG_FILE   = "/home/srwang/testenv/20260403/1915_Taihoku_Cho.svg"
OUTPUT_FILE= "/home/srwang/testenv/20260403/1915_Taihoku_Cho.geojson"

# ── New Taipei City reference points (WGS84) ──────────────────────────────────
# Extreme East:  貢寮區澳底附近  (easternmost longitude + its latitude)
NTPC_E_LON = 122.0076
NTPC_E_LAT =  25.008286
# Extreme North: 石門區富貴角附近 (northernmost latitude + its longitude)
NTPC_N_LON = 121.577008
NTPC_N_LAT =  25.298403

SVG_NS      = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"


def parse_translate(t):
    m = re.search(r'translate\(\s*([-\d.e+]+)\s*,\s*([-\d.e+]+)\s*\)', t or '')
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)

def tokenize(d):
    return re.findall(r'[MmLlHhVvCcZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', d)

def bezier(p0, p1, p2, p3, steps=10):
    return [((1-t)**3*p0[0]+3*(1-t)**2*t*p1[0]+3*(1-t)*t**2*p2[0]+t**3*p3[0],
             (1-t)**3*p0[1]+3*(1-t)**2*t*p1[1]+3*(1-t)*t**2*p2[1]+t**3*p3[1])
            for t in (i/steps for i in range(1, steps+1))]

def parse_path(d, tx=0.0, ty=0.0):
    tokens = tokenize(d); n = len(tokens); i = 0
    cmd = None; cx = cy = sx = sy = 0.0; rings = []; cur = []
    def nf():
        nonlocal i; v = float(tokens[i]); i += 1; return v
    while i < n:
        tok = tokens[i]
        if re.match(r'^[MmLlHhVvCcZz]$', tok): cmd = tok; i += 1
        if cmd == 'M':
            if len(cur) >= 3: rings.append(cur)
            cur = []; cx = nf(); cy = nf(); sx, sy = cx, cy
            cur.append((cx+tx, cy+ty)); cmd = 'L'
        elif cmd == 'm':
            if len(cur) >= 3: rings.append(cur)
            cur = []; cx += nf(); cy += nf(); sx, sy = cx, cy
            cur.append((cx+tx, cy+ty)); cmd = 'l'
        elif cmd == 'L': cx = nf(); cy = nf(); cur.append((cx+tx, cy+ty))
        elif cmd == 'l': cx += nf(); cy += nf(); cur.append((cx+tx, cy+ty))
        elif cmd == 'H': cx = nf(); cur.append((cx+tx, cy+ty))
        elif cmd == 'h': cx += nf(); cur.append((cx+tx, cy+ty))
        elif cmd == 'V': cy = nf(); cur.append((cx+tx, cy+ty))
        elif cmd == 'v': cy += nf(); cur.append((cx+tx, cy+ty))
        elif cmd == 'C':
            x1,y1=nf(),nf(); x2,y2=nf(),nf(); x3,y3=nf(),nf()
            for p in bezier((cx,cy),(x1,y1),(x2,y2),(x3,y3)): cur.append((p[0]+tx,p[1]+ty))
            cx, cy = x3, y3
        elif cmd == 'c':
            dx1,dy1=nf(),nf(); dx2,dy2=nf(),nf(); dx3,dy3=nf(),nf()
            for p in bezier((cx,cy),(cx+dx1,cy+dy1),(cx+dx2,cy+dy2),(cx+dx3,cy+dy3)):
                cur.append((p[0]+tx, p[1]+ty))
            cx += dx3; cy += dy3
        elif cmd in ('Z','z'):
            if len(cur) >= 3: rings.append(cur)
            cur = []; cx, cy = sx, sy
        else: i += 1
    if len(cur) >= 3: rings.append(cur)
    return rings


# ── Parse SVG paths ────────────────────────────────────────────────────────────
tree = ET.parse(SVG_FILE)
root = tree.getroot()
features = []
all_pts = []

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
            style = path.get('style','')
            if not path.get('d') or 'fill:none' in style: continue
            rings = parse_path(path.get('d'), ltx+gtx, lty+gty)
            if not rings: continue
            fill = (re.search(r'fill:(#[0-9a-fA-F]+)', style) or [None,None])[1] or '#cccccc'
            features.append({
                "type": "Feature",
                "properties": {"id": path.get('id',''), "fill": fill},
                "geometry": {"type": "Polygon",
                             "coordinates": [[[p[0],p[1]] for p in r] for r in rings]}
            })
            for r in rings: all_pts.extend(r)

print(f"Parsed {len(features)} features, {len(all_pts)} total points")

# ── Find SVG extreme points ────────────────────────────────────────────────────
east_pt  = max(all_pts, key=lambda p: p[0])   # rightmost x  → extreme East
north_pt = min(all_pts, key=lambda p: p[1])   # topmost y    → extreme North

ex, ey = east_pt
nx, ny = north_pt
print(f"SVG extreme East:  ({ex:.4f}, {ey:.4f})")
print(f"SVG extreme North: ({nx:.4f}, {ny:.4f})")

# ── Two-point alignment (non-uniform scale + translate, no rotation) ───────────
# lon = scaleX * px + tx
# lat = -scaleY * py + ty   (SVG y↓ is inverted vs latitude↑)
#
# East  point: (ex, ey) → (NTPC_E_LON, NTPC_E_LAT)
# North point: (nx, ny) → (NTPC_N_LON, NTPC_N_LAT)
#
# scaleX from lon equations:
scaleX = (NTPC_E_LON - NTPC_N_LON) / (ex - nx)
tx     = NTPC_E_LON - scaleX * ex

# scaleY from lat equations:
scaleY = (NTPC_N_LAT - NTPC_E_LAT) / (ey - ny)
ty     = NTPC_E_LAT + scaleY * ey

print(f"\nTransform: scaleX={scaleX:.8f}  scaleY={scaleY:.8f}")
print(f"           tx={tx:.6f}  ty={ty:.6f}")

# Verify
print(f"\nVerification:")
print(f"  East  → lon={scaleX*ex+tx:.6f} (expect {NTPC_E_LON}), lat={-scaleY*ey+ty:.6f} (expect {NTPC_E_LAT})")
print(f"  North → lon={scaleX*nx+tx:.6f} (expect {NTPC_N_LON}), lat={-scaleY*ny+ty:.6f} (expect {NTPC_N_LAT})")

def to_geo(px, py):
    return [round(scaleX*px + tx, 6), round(-scaleY*py + ty, 6)]

# ── Apply transform ────────────────────────────────────────────────────────────
for feat in features:
    feat['geometry']['coordinates'] = [
        [to_geo(p[0], p[1]) for p in ring]
        for ring in feat['geometry']['coordinates']
    ]

# ── Write GeoJSON ─────────────────────────────────────────────────────────────
geojson = {
    "type": "FeatureCollection",
    "name": "1915_Taihoku_Cho",
    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
    "features": features
}
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(geojson, f, ensure_ascii=False, separators=(',', ':'))

sz = len(open(OUTPUT_FILE).read())
print(f"\nSaved → {OUTPUT_FILE}  ({sz/1024:.1f} KB)")
