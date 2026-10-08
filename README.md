# Masking Pipeline

从给定 GPS 坐标生成 routing land-cover masking 图的完整流水线。

本目录是从 `image_process/` 复制整理而来的**独立可运行包**，不依赖仓库其它代码。原有 `image_process/` 脚本保持不动。

## 流程

```
坐标 (lat, lon)
    │
    ▼
[1] download.py     下载 ESRI World Imagery → GeoTIFF + preview PNG
    │
    ▼
[2] segment.py      Mask2Former 分割 → fine/coarse .npy + overlay PNG
    │
    ▼
[3] downsample.py   最近邻下采样到目标网格 (默认 1800×1800) + legend PNG
```

路由粗类别 (`ROUTE_CLASSES`):

| id | name              | color   |
|----|-------------------|---------|
| 0  | other             | #666666 |
| 1  | field             | #f2d16b |
| 2  | building          | #d81b60 |
| 3  | road              | #ff4d4d |
| 4  | mountain_natural  | #2ecc71 |
| 5  | water             | #1f5fd1 |

## 安装

```bash
cd masking_pipeline
# 推荐：本仓库已有 conda 环境
conda activate route_plan

# 或新建环境
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

- 分割步骤有 GPU（CUDA）会更快；无 GPU 时自动用 CPU（较慢）。
- 国内默认使用 HuggingFace 镜像 `https://hf-mirror.com` 拉取模型 `mfaytin/mask2former-satellite`。
- 本包已在 `route_plan` 环境下跑通 download → segment → downsample。

## 一键运行

```bash
cd masking_pipeline

python run.py --lat 27.501662 --lon 120.194639

# 自定义范围 / 分辨率 / 输出目录
python run.py \
  --lat 27.55 --lon 120.38 \
  --radius-km 0.9 \
  --zoom 18 \
  --target-height 1800 --target-width 1800 \
  --output-dir ./my_site_out

# 仅跑某一步（需已有上游产物）
python run.py --lat 27.55 --lon 120.38 --step download
python run.py --lat 27.55 --lon 120.38 --step segment --output-dir ./my_site_out
python run.py --lat 27.55 --lon 120.38 --step downsample --output-dir ./my_site_out

# 直连 huggingface.co（不用镜像）
python run.py --lat 27.55 --lon 120.38 --hf-endpoint ""
```

## 主要输出

在 `--output-dir`（默认 `outputs_lat{lat}_lon{lon}_{YYYYMMDD}/`）下：

| 文件 | 说明 |
|------|------|
| `*_epsg3857.tif` | 卫星 GeoTIFF |
| `*_preview.png` | 卫星预览图 |
| `*_openearthmap_fine.png` | 细类叠加可视化 |
| `*_routing_coarse.png` | 粗类叠加可视化（masking 图） |
| `*_routing_coarse_mask.npy` | 全分辨率粗类 mask |
| `*_routing_coarse_mask_class_map.png` | 全分辨率纯色类别图 |
| `*_routing_coarse_downsampled.png` | 下采样后 masking 图 |
| `*_routing_coarse_mask_downsampled.npy` | 下采样 mask（可直接用于路径规划） |

## 作为库调用

```python
from run import run_pipeline

results = run_pipeline(lat=27.501662, lon=120.194639)
print(results["coarse_vis"])
print(results["downsampled_npy"])
```

## 文件说明

| 文件 | 来源 | 作用 |
|------|------|------|
| `run.py` | 新建 | 统一入口 |
| `download.py` | `image_process/download_satellite_geotiff.py` | 瓦片下载 |
| `segment.py` | `image_process/segment_landcover_routing.py` | 地物分割 |
| `downsample.py` | `image_process/downsample_to_mask_gray.py` | 下采样 |
| `render.py` | `image_process/render_routing_coarse_mask_to_png.py` | 纯色类别图渲染 |
