#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup-lens-backend FastAPI — Linux Docker, python:3.8, PyAutoLens 2021.10.14.1 strong lock.
Endpoints for setup-lens-frontend (pure static index.html on GitHub Pages).
"""
import logging
import warnings
warnings.filterwarnings("ignore")
logging.getLogger("autoconf").setLevel(logging.ERROR)

from typing import Optional, List, Dict, Any
import numpy as np

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .lensing import (
    DEFAULTS, BEAM_DEFAULTS,
    GRID_SHAPE_STATIC, GRID_PIXEL_SCALE_STATIC,
    GRID_SHAPE_DRAG, GRID_PIXEL_SCALE_DRAG,
    build_tracer, compute_images, compute_critical_caustics_from_grid,
    create_beam_kernel, convolve_image,
    array_to_blues_png_base64, curves_to_lists,
)

app = FastAPI(title="setup-lens-backend", version="1.0.0")

# CORS open by default; restrict via CORS_ORIGIN env in production (Render/Railway/Fly)
import os
_cors_origins = os.environ.get("CORS_ORIGIN", "*")
if _cors_origins == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache for critical/caustics keyed by lens params + grid
_cc_cache: Dict[Any, Any] = {}


def _lens_key(params: dict):
    return (
        params["lens_e_y"], params["lens_e_x"], params["einstein_radius"], params["slope"],
        params["shear_e_y"], params["shear_e_x"], params["redshift_l"], params["redshift_s"],
    )


class ComputeRequest(BaseModel):
    params: Dict[str, float] = Field(default_factory=lambda: dict(DEFAULTS))
    grid_shape: int = GRID_SHAPE_STATIC
    pixel_scale: float = GRID_PIXEL_SCALE_STATIC
    high_res: Optional[bool] = None  # if set, overrides grid_shape/pixel_scale
    bmaj: float = BEAM_DEFAULTS["bmaj"]
    bmin: float = BEAM_DEFAULTS["bmin"]
    pa: float = BEAM_DEFAULTS["pa"]
    apply_beam: bool = False
    with_critical: bool = True
    with_caustics: bool = True


class HealthResponse(BaseModel):
    status: str
    autolens: str
    python: str


@app.get("/api/health", response_model=HealthResponse)
def health():
    import sys
    try:
        import autolens as al
        al_ver = getattr(al, "__version__", "unknown")
    except Exception:
        al_ver = "missing"
    return {"status": "ok", "autolens": al_ver, "python": sys.version.split()[0]}


@app.get("/")
def root():
    return {"service": "setup-lens-backend", "docs": "/docs", "health": "/api/health"}


@app.post("/api/compute")
def compute(req: ComputeRequest):
    # Resolve grid: high_res flag takes precedence (matches desktop drag/static)
    if req.high_res is True:
        grid_shape, pixel_scale = GRID_SHAPE_STATIC, GRID_PIXEL_SCALE_STATIC
    elif req.high_res is False:
        grid_shape, pixel_scale = GRID_SHAPE_DRAG, GRID_PIXEL_SCALE_DRAG
    else:
        grid_shape, pixel_scale = int(req.grid_shape), float(req.pixel_scale)

    if grid_shape not in (150, 200, 300, 301) and not (50 <= grid_shape <= 600):
        raise HTTPException(status_code=422, detail="grid_shape must be 50..600")
    if not (0.005 <= pixel_scale <= 0.1):
        raise HTTPException(status_code=422, detail="pixel_scale must be 0.005..0.1")

    # Merge params with defaults + validate
    params = dict(DEFAULTS)
    for k, v in (req.params or {}).items():
        if k not in DEFAULTS:
            raise HTTPException(status_code=422, detail=f"unknown param {k}")
        try:
            params[k] = float(v)
        except Exception:
            raise HTTPException(status_code=422, detail=f"param {k} must be numeric")

    if req.apply_beam:
        if req.bmaj <= 0 or req.bmin <= 0:
            raise HTTPException(status_code=422, detail="Bmaj/Bmin must be >0")

    try:
        image, extent_image, plane_image, extent_source, tracer, grid, traced = compute_images(
            params, grid_shape=grid_shape, pixel_scale=pixel_scale
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"compute_images failed: {e}")

    img_native = np.array(image.native, dtype=np.float64)
    src_native = np.array(plane_image.native, dtype=np.float64)

    # Beam convolve image plane only (source stays intrinsic)
    kernel_shape = None
    display_native = img_native
    is_convolved = False
    if req.apply_beam:
        try:
            kernel = create_beam_kernel(req.bmaj, req.bmin, req.pa, pixel_scale)
            kernel_shape = [int(kernel.shape[0]), int(kernel.shape[1])]
            display_native = np.asarray(convolve_image(img_native, kernel), dtype=np.float64)
            is_convolved = True
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"beam convolve failed: {e}")

    # PNG base64 with Blues (no axes, origin upper preserved)
    try:
        image_b64, image_vmin, image_vmax = array_to_blues_png_base64(display_native, origin="upper")
        source_b64, source_vmin, source_vmax = array_to_blues_png_base64(src_native, origin="upper")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"png encode failed: {e}")

    # Critical / caustics from SAME tracer+grid (same system), cached
    critical_curves: List = []
    caustics: List = []
    if req.with_critical or req.with_caustics:
        key = (_lens_key(params), (tuple(grid.shape_native), tuple(grid.pixel_scales)),
               bool(req.with_critical), bool(req.with_caustics))
        if key in _cc_cache:
            cc, ca = _cc_cache[key]
        else:
            cc, ca = compute_critical_caustics_from_grid(tracer, grid)
            _cc_cache[key] = (cc, ca)
            # cap cache
            if len(_cc_cache) > 32:
                _cc_cache.pop(next(iter(_cc_cache)))
        if req.with_critical:
            critical_curves = curves_to_lists(cc)
        if req.with_caustics:
            caustics = curves_to_lists(ca)

    # Beam ellipse for frontend corner patch (same convention angle=90+PA)
    x0, x1, y0, y1 = [float(v) for v in extent_image]
    beam_ellipse = None
    if req.apply_beam or True:  # always return geometry so frontend can preview
        beam_ellipse = {
            "x": x0 + (x1 - x0) * 0.12,
            "y": y0 + (y1 - y0) * 0.12,
            "width": float(req.bmaj),
            "height": float(req.bmin),
            "angle": float(90.0 + req.pa),
            "label": f"Beam {req.bmaj:.2f}x{req.bmin:.2f} PA{req.pa:.0f}",
        }

    return {
        "image": {
            "png_base64": image_b64,
            "extent": [float(v) for v in extent_image],
            "shape": [int(grid_shape), int(grid_shape)],
            "pixel_scale": float(pixel_scale),
            "vmin": float(image_vmin),
            "vmax": float(image_vmax),
            "max": float(np.max(display_native)),
            "is_convolved": bool(is_convolved),
        },
        "source": {
            "png_base64": source_b64,
            "extent": [float(v) for v in extent_source],
            "shape": [int(grid_shape), int(grid_shape)],
            "vmin": float(source_vmin),
            "vmax": float(source_vmax),
            "max": float(np.max(src_native)),
        },
        "critical_curves": critical_curves,
        "caustics": caustics,
        "beam_ellipse": beam_ellipse,
        "beam": {"bmaj": float(req.bmaj), "bmin": float(req.bmin), "pa": float(req.pa),
                 "kernel_shape": kernel_shape, "applied": bool(is_convolved)},
        "grid": {"shape": int(grid_shape), "pixel_scale": float(pixel_scale)},
        "params_echo": params,
    }
