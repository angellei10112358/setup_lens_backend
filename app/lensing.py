#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
setup-lens-backend lensing core — ported verbatim from adhoc_jobs/lensing_gui/app.py:66-180
No physics rewrite. PyAutoLens 2021.10.14.1 only. Matplotlib Agg for headless PNG.
"""
import io
import base64
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm

import autolens as al

GRID_SHAPE_STATIC = 300
GRID_PIXEL_SCALE_STATIC = 0.02
GRID_SHAPE_DRAG = 150
GRID_PIXEL_SCALE_DRAG = 0.04

DEFAULTS = {
    "lens_e_y": -0.137,
    "lens_e_x": -0.265,
    "einstein_radius": 0.645,
    "slope": 1.895,
    "shear_e_y": 0.033,
    "shear_e_x": -0.055,
    "source_centre_y": 0.0,
    "source_centre_x": 0.0,
    "source_e_y": 0.001,
    "source_e_x": 0.001,
    "intensity": 1.7,
    "effective_radius": 0.063,
    "sersic_index": 0.639,
    "redshift_l": 1.7,
    "redshift_s": 2.5579,
}

BEAM_DEFAULTS = {"bmaj": 0.15, "bmin": 0.10, "pa": 30.0}


def build_tracer(params):
    lens = al.Galaxy(
        redshift=params["redshift_l"],
        mass=al.mp.EllPowerLaw(
            elliptical_comps=(params["lens_e_y"], params["lens_e_x"]),
            einstein_radius=params["einstein_radius"],
            slope=params["slope"],
        ),
        shear=al.mp.ExternalShear(
            elliptical_comps=(params["shear_e_y"], params["shear_e_x"])
        ),
    )
    source = al.Galaxy(
        redshift=params["redshift_s"],
        bulge=al.lp.EllSersic(
            centre=(params["source_centre_y"], params["source_centre_x"]),
            elliptical_comps=(params["source_e_y"], params["source_e_x"]),
            intensity=params["intensity"],
            effective_radius=params["effective_radius"],
            sersic_index=params["sersic_index"],
        ),
    )
    return al.Tracer.from_galaxies(galaxies=[lens, source])


def compute_images(params, grid_shape=GRID_SHAPE_STATIC, pixel_scale=GRID_PIXEL_SCALE_STATIC):
    tracer = build_tracer(params)
    grid = al.Grid2D.uniform(shape_native=(grid_shape, grid_shape), pixel_scales=pixel_scale)
    image = tracer.image_2d_from(grid=grid)
    traced_grids = tracer.traced_grids_of_planes_from(grid=grid)
    traced_source_grid = traced_grids[1]
    plane_image_obj = tracer.planes[1].plane_image_2d_from(grid=traced_source_grid)
    plane_image = plane_image_obj.array
    extent_image = [float(v) for v in image.extent]
    extent_source = [float(v) for v in plane_image.extent]
    return image, extent_image, plane_image, extent_source, tracer, grid, traced_source_grid


def compute_critical_caustics_from_grid(tracer, grid):
    try:
        cc = tracer.critical_curves_from(grid=grid, pixel_scale=0.05)
    except Exception as e:
        print(f"critical_curves error {e}")
        cc = []
    try:
        ca = tracer.caustics_from(grid=grid, pixel_scale=0.05)
    except Exception as e:
        print(f"caustics error {e}")
        ca = []
    return cc, ca


def create_beam_kernel(bmaj, bmin, pa_deg, pixel_scale):
    """
    Radio CASA/AIPS: Bmaj/Bmin=FWHM("), PA=N->E, 0=N-S, 90=E-W, East=-x (left).
    World orientation theta_math = 90 + PA (same as the ellipse patch). The kernel
    array itself is built with -theta_math because array rows point DOWN while the
    displayed world y points UP (origin="upper"); without the negation the convolved
    image comes out mirrored (PA sign flipped).
    """
    if bmaj <= 0 or bmin <= 0:
        raise ValueError("Bmaj/Bmin must be >0")
    sigma_maj = bmaj / (2 * np.sqrt(2 * np.log(2))) / pixel_scale
    sigma_min = bmin / (2 * np.sqrt(2 * np.log(2))) / pixel_scale
    radius = int(np.ceil(4 * max(sigma_maj, sigma_min)))
    size = 2 * radius + 1
    size = max(5, min(size, 101))
    if size % 2 == 0:
        size += 1
    y, x = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    # y here is the array row offset (points DOWN); negate so the kernel lands on
    # the same world orientation as the ellipse patch drawn with angle=90+PA.
    theta = np.deg2rad(-90.0 - pa_deg)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)
    x_rot = x * cos_t + y * sin_t
    y_rot = -x * sin_t + y * cos_t
    kernel = np.exp(-0.5 * ((x_rot / sigma_maj) ** 2 + (y_rot / sigma_min) ** 2))
    kernel /= np.sum(kernel)
    return kernel


def convolve_image(image_native, kernel):
    try:
        from scipy.signal import fftconvolve
        return fftconvolve(image_native, kernel, mode="same")
    except Exception:
        from astropy.convolution import convolve as apy_convolve
        return apy_convolve(image_native, kernel, boundary="fill", fill_value=0.0)


def array_to_blues_png_base64(arr2d, origin="upper"):
    """
    Apply matplotlib Blues colormap (same as desktop imshow cmap="Blues") and
    encode as PNG base64 WITHOUT axes. Frontend stretches to extent.
    origin is preserved: row0 stays on top (native row0=y_max). Frontend must use same.
    Returns (b64_str, vmin, vmax).
    """
    arr = np.asarray(arr2d, dtype=np.float64)
    vmin = float(np.min(arr))
    vmax = float(np.max(arr))
    if vmax <= vmin:
        norm = np.zeros_like(arr)
    else:
        norm = (arr - vmin) / (vmax - vmin)
    # Blues colormap
    cmap = cm.get_cmap("Blues")
    rgba = cmap(norm)  # HxWx4 float
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    # PIL save
    from PIL import Image
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return b64, vmin, vmax


def curves_to_lists(curves):
    """Convert Grid2DIrregular/list of (y,x) arrays to JSON-serializable lists."""
    out = []
    if curves is None:
        return out
    try:
        for c in curves:
            if c is None:
                continue
            arr = np.array(c, dtype=np.float64)
            if arr.size == 0 or arr.shape[0] < 2:
                continue
            # arr shape (N,2) with (y,x)
            out.append(arr.tolist())
    except Exception as e:
        print(f"curves_to_lists error {e}")
    return out
