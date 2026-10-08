#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-end pipeline: GPS coordinates → satellite GeoTIFF → land-cover masking figures.

Steps
-----
1. Download ESRI World Imagery tiles around (lat, lon) as a GeoTIFF.
2. Segment with Mask2Former (OpenEarthMap) → fine + coarse routing masks + overlay PNGs.
3. Downsample the coarse mask to a target grid (default 1800×1800) + legend PNG.

Example
-------
  cd masking_pipeline
  python run.py --lat 27.501662 --lon 120.194639

  # China HF mirror (default on):
  python run.py --lat 27.55 --lon 120.38 --hf-endpoint https://hf-mirror.com

  # Skip download / segment if outputs already exist:
  python run.py --lat 27.55 --lon 120.38 --step downsample
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from typing import Optional

try:
    from download import download_satellite_geotiff
    from downsample import downsample_routing_mask
    from render import build_palette, mask_to_rgb, save_legend_png
    from segment import run_segmentation
except ImportError:  # when imported as masking_pipeline.run
    from .download import download_satellite_geotiff
    from .downsample import downsample_routing_mask
    from .render import build_palette, mask_to_rgb, save_legend_png
    from .segment import run_segmentation

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def build_stem(lat: float, lon: float, radius_km: float, zoom: int, crop: bool = True) -> str:
    return (
        f"satellite_{lat:.6f}_{lon:.6f}_r{radius_km:.2f}km_z{zoom}"
        f"_{'crop' if crop else 'full'}"
    )


def default_output_dir(lat: float, lon: float, date: Optional[str] = None) -> str:
    date = date or datetime.now().strftime("%Y%m%d")
    return os.path.join(SCRIPT_DIR, f"outputs_lat{lat:.6f}_lon{lon:.6f}_{date}")


def render_fullres_class_map(coarse_npy: str, output_dir: str) -> dict:
    """Write full-resolution RGB class map + legend next to the coarse mask."""
    import numpy as np
    from pathlib import Path
    from PIL import Image

    npy_path = Path(coarse_npy)
    mask = np.load(str(npy_path), allow_pickle=True)
    if mask.ndim != 2:
        raise ValueError(f"Expected 2D mask, got shape {mask.shape}")

    rgb = mask_to_rgb(mask, build_palette())
    out_png = Path(output_dir) / f"{npy_path.stem}_class_map.png"
    leg_png = Path(output_dir) / f"{npy_path.stem}_class_map_legend.png"
    Image.fromarray(rgb, mode="RGB").save(out_png, compress_level=6)
    save_legend_png(leg_png)
    print(f"Wrote class map: {out_png}")
    print(f"Wrote legend:    {leg_png}")
    return {"class_map_png": str(out_png), "legend_png": str(leg_png)}


def run_pipeline(
    lat: float,
    lon: float,
    radius_km: float = 0.9,
    zoom: int = 18,
    target_height: int = 1800,
    target_width: int = 1800,
    output_dir: Optional[str] = None,
    model: str = "mfaytin/mask2former-satellite",
    hf_endpoint: Optional[str] = "https://hf-mirror.com",
    step: str = "all",
    overwrite: bool = True,
    render_fullres: bool = True,
) -> dict:
    """
    Run the full coordinate → masking pipeline.

    Returns a dict of key output paths.
    """
    out_dir = os.path.abspath(output_dir) if output_dir else default_output_dir(lat, lon)
    os.makedirs(out_dir, exist_ok=True)

    stem = build_stem(lat, lon, radius_km, zoom, crop=True)
    tif_path = os.path.join(out_dir, f"{stem}_epsg3857.tif")
    coarse_npy = os.path.join(out_dir, f"{stem}_epsg3857_routing_coarse_mask.npy")

    results = {"output_dir": out_dir, "stem": stem}

    print("=" * 60)
    print("Masking pipeline: coordinates → masking figures")
    print(f"  lat/lon:     {lat:.6f}, {lon:.6f}")
    print(f"  radius_km:   {radius_km}  (square side {radius_km * 2:.2f} km)")
    print(f"  zoom:        {zoom}")
    print(f"  target grid: {target_height} x {target_width}")
    print(f"  output_dir:  {out_dir}")
    print(f"  model:       {model}")
    print(f"  step:        {step}")
    print("=" * 60)

    # --- Step 1: download ---
    if step in ("all", "download"):
        print("\n>>> [1/3] Download satellite GeoTIFF")
        meta = download_satellite_geotiff(
            center_lat=lat,
            center_lon=lon,
            radius_km=radius_km,
            zoom=zoom,
            output_dir=out_dir,
            crop_to_request=True,
            save_preview=True,
            overwrite=overwrite,
        )
        tif_path = meta.output_geotiff
        results["geotiff"] = tif_path
        results["preview_png"] = meta.output_preview_png
        results["meta_json"] = meta.output_metadata_json
    else:
        if not os.path.isfile(tif_path):
            raise FileNotFoundError(f"GeoTIFF not found: {tif_path}. Run with --step download|all first.")
        results["geotiff"] = tif_path

    # --- Step 2: segment ---
    if step in ("all", "segment"):
        print("\n>>> [2/3] Land-cover segmentation → masking figures")
        seg = run_segmentation(
            image=tif_path,
            output_dir=out_dir,
            model=model,
            hf_endpoint=hf_endpoint,
        )
        coarse_npy = seg["coarse_npy"]
        results.update(
            {
                "fine_npy": seg["fine_npy"],
                "coarse_npy": seg["coarse_npy"],
                "fine_vis": seg["fine_vis"],
                "coarse_vis": seg["coarse_vis"],
            }
        )
        if render_fullres:
            results.update(render_fullres_class_map(coarse_npy, out_dir))
    else:
        if step == "downsample" and not os.path.isfile(coarse_npy):
            raise FileNotFoundError(
                f"Coarse mask not found: {coarse_npy}. Run with --step segment|all first."
            )
        if os.path.isfile(coarse_npy):
            results["coarse_npy"] = coarse_npy

    # --- Step 3: downsample ---
    if step in ("all", "downsample"):
        print(f"\n>>> [3/3] Downsample to {target_height}x{target_width}")
        down = downsample_routing_mask(
            coarse_npy=coarse_npy,
            output_dir=out_dir,
            target_height=target_height,
            target_width=target_width,
            save_png=True,
        )
        results["downsampled_npy"] = down["downsampled_npy"]
        results["downsampled_png"] = down.get("downsampled_png")
        results["downsampled_shape"] = down["shape"]

    print("\n=== done ===")
    print(f"  output_dir:      {out_dir}")
    for key in (
        "geotiff",
        "preview_png",
        "fine_vis",
        "coarse_vis",
        "class_map_png",
        "downsampled_png",
        "downsampled_npy",
        "coarse_npy",
    ):
        if results.get(key):
            print(f"  {key:16s} {results[key]}")
    return results


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="GPS coordinates → satellite download → land-cover masking figures",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--lat", type=float, required=True, help="Center latitude (WGS84)")
    p.add_argument("--lon", type=float, required=True, help="Center longitude (WGS84)")
    p.add_argument("--radius-km", type=float, default=0.9, help="Half-side of square bbox in km")
    p.add_argument("--zoom", type=int, default=18, help="XYZ tile zoom level")
    p.add_argument("--target-height", type=int, default=1800, help="Downsampled mask height")
    p.add_argument("--target-width", type=int, default=1800, help="Downsampled mask width")
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output folder (default: masking_pipeline/outputs_lat..._lon..._YYYYMMDD)",
    )
    p.add_argument(
        "--model",
        type=str,
        default="mfaytin/mask2former-satellite",
        help="HuggingFace model id or local path",
    )
    p.add_argument(
        "--hf-endpoint",
        type=str,
        default="https://hf-mirror.com",
        help="HF Hub mirror (set empty string to use huggingface.co)",
    )
    p.add_argument(
        "--step",
        type=str,
        default="all",
        choices=["all", "download", "segment", "downsample"],
        help="Run full pipeline or a single stage",
    )
    p.add_argument("--no-overwrite", action="store_true", help="Fail if GeoTIFF already exists")
    p.add_argument(
        "--no-fullres-render",
        action="store_true",
        help="Skip writing full-resolution class_map PNG",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    hf = (args.hf_endpoint or "").strip() or None
    run_pipeline(
        lat=args.lat,
        lon=args.lon,
        radius_km=args.radius_km,
        zoom=args.zoom,
        target_height=args.target_height,
        target_width=args.target_width,
        output_dir=args.output_dir,
        model=args.model,
        hf_endpoint=hf,
        step=args.step,
        overwrite=not args.no_overwrite,
        render_fullres=not args.no_fullres_render,
    )


if __name__ == "__main__":
    main()
