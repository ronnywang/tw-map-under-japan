# 1915 台北廳行政區劃 GeoJSON 資料清理記錄

## 資料來源

- **原始 SVG**：[Wikipedia — 1915 Taihoku Cho.svg](https://commons.wikimedia.org/wiki/File:1915_Taihoku_Cho.svg)
  - 繪製工具：Inkscape
  - 畫布尺寸：1200 × 800 px
  - 內容：1915 年台北廳行政區劃圖，含 14 個支廳（＋廳直轄）及其下轄各區的白線分割

---

## 處理流程

### 第一步：SVG 路徑解析

使用 Python 標準庫（`xml.etree.ElementTree`、`re`）解析 SVG，不依賴外部套件。

- 套用 SVG layer/group 的 `translate()` transform
- 解析 `M/m/L/l/H/h/V/v/C/c/Z/z` 路徑指令
- 貝茲曲線（`C/c`）以 12 段折線取樣近似
- 篩選：
  - **彩色填充路徑**（14 條）→ 支廳多邊形
  - **白色筆劃路徑**（52 條）→ 區界分割線（`fill:none; stroke:#ffffff`）

### 第二步：座標對齊

採用**兩點對齊法**，將 SVG 像素座標轉換為 WGS84 經緯度：

| 對齊點 | SVG 像素座標 | 對應地理座標 |
|--------|-------------|-------------|
| 極東點 | (1161.33, 489.84) | 122.0076°E, 25.008286°N |
| 極北點 | (538.80, 69.13)   | 121.577008°E, 25.298403°N |

轉換公式（非等比縮放 + 平移，無旋轉）：

```
lon = scaleX × px + tx
lat = −scaleY × py + ty

scaleX = (E_lon − N_lon) / (px_east − px_north)
scaleY = (N_lat − E_lat) / (py_east − py_north)
```

### 第三步：支廳命名（手動）

產生 `label_tool.html`：
- 左側：互動 Canvas 地圖（點擊多邊形高亮）
- 右側：14 個多邊形清單，各有下拉選單（選項從 SVG 文字標籤自動擷取）
- 底部：原始 SVG 參考圖 ＋ 輸出 JSON 按鈕

產出 `1915支廳.geojson`（14 個 features）。

### 第四步：區多邊形分割

使用 **Shapely 2.x** 對每個支廳多邊形沿白線進行多邊形切割：

```python
from shapely.ops import split

# 對每條白線向兩端延伸 8px 確保穿越邊界
# 對每個支廳多邊形依序套用所有與之相交的白線進行 split
# 過濾面積 < 原多邊形 0.5% 的碎片
```

共切割出 **53 個區多邊形**。

### 第五步：區名自動配對

- 從 SVG `圖層` layer 擷取所有黑色文字標籤（排除紅色支廳名、標題、圖例）
- 以**連通元件聚類**（閾值 40px）合併垂直排列的單字漢字
- 特殊處理：`a` → 艋舺區、`b` → 大稻埕區
- 對每個區多邊形進行 point-in-polygon 測試（以文字座標對應 Shapely Polygon）

自動配對成功 50 個，剩餘 3 個未命名。

### 第六步：區名確認（手動）

產生 `label_tool_2.html`：
- 左側：Canvas 顯示 53 個區多邊形（以父支廳顏色半透明填充），可點擊
- 右側：所有區的 textbox 清單，預填自動配對結果，分組顯示
- SVG 底圖半透明疊加供對照
- 輸出 JSON 供最終更新

---

## 最終產出

| 檔案 | 說明 |
|------|------|
| `1915支廳.geojson` | 14 個支廳多邊形，含 `name`、`fill` |
| `1915區.geojson`   | 53 個區多邊形，含 `name`、`parent_name`、`fill` |

### GeoJSON properties 說明

**1915支廳.geojson**
```json
{
  "id": "rect3633",
  "name": "新庄支廳",
  "fill": "#ffc1c1"
}
```

**1915區.geojson**
```json
{
  "id": "dist_0",
  "name": "五股坑區",
  "parent_id": "rect3633",
  "parent_name": "新庄支廳",
  "fill": "#ffc1c1"
}
```

---

## 工具腳本

| 腳本 | 用途 |
|------|------|
| `svg_to_geojson.py` | SVG → 支廳 GeoJSON（路徑解析 ＋ 座標對齊） |
| `make_district.py`  | 區多邊形切割、自動命名、產生 label tool |
| `label_tool.html`   | 支廳命名互動介面 |
| `label_tool_2.html` | 區名確認互動介面 |
