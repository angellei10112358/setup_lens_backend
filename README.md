# setup-lens-backend

Linux Docker backend, reusing the physics from `adhoc_jobs/lensing_gui/app.py:66-180` verbatim (**no PyAutoLens rewrite**), serving the pure-static frontend.

- Base: `python:3.8-slim-bullseye` (glibc), strong lock on `autolens==2021.10.14.1` + `numpy==1.20.2` (see `requirements.txt`)
- Headless rendering with `matplotlib Agg`, Beam convolution via `scipy.fftconvolve`
- Critical/caustic share the same `tracer+grid` as imaging (same system), `PA=90+PA` (east=-x left, sign corrected)

## Run locally (Windows smoke test with .venv, Linux with Docker)

```bat
REM Windows smoke (project .venv reuses Anaconda autolens)
G:\OpenCode\context-infrastructure\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir G:\OpenCode\context-infrastructure\adhoc_jobs\setup_lens_backend
```

```bash
# Linux Docker
docker build -t setup-lens-backend .
docker run -p 8000:8000 -e CORS_ORIGIN="https://YOUR_GITHUB_USERNAME.github.io" setup-lens-backend
curl http://127.0.0.1:8000/api/health
```

## API

- `GET /api/health` → `{status, autolens, python}`
- `POST /api/compute`
  Request:
  ```json
  {
    "params": {"lens_e_y":-0.137,"lens_e_x":-0.265,"einstein_radius":0.645,"slope":1.895,"shear_e_y":0.033,"shear_e_x":-0.055,"source_centre_y":-0.05,"source_centre_x":0.08,"source_e_y":0.001,"source_e_x":0.001,"intensity":1.7,"effective_radius":0.063,"sersic_index":0.639,"redshift_l":1.7,"redshift_s":2.5579},
    "high_res": true,
    "bmaj": 0.15, "bmin": 0.10, "pa": 30.0, "apply_beam": false,
    "with_critical": true, "with_caustics": true
  }
  ```
  Response: `{image:{png_base64,extent,shape,pixel_scale,vmin,vmax,max,is_convolved}, source:{...}, critical_curves:[[[y,x]...]], caustics:[...], beam_ellipse:{x,y,width,height,angle}, beam:{...}, grid, params_echo}`

  - `png_base64` is a `Blues` PNG without axes (`origin="upper"`, row0=y_max); the frontend stretches it by `extent=[x0,x1,y0,y1]`
  - `critical_curves`/`caustics` are world-coordinate `(y,x)` polylines; the frontend just does `plot(x,y)`
  - `high_res:true→300@0.02, false→150@0.04` (same ±3" field of view, no jitter while dragging)

## Deploy

- **Render**: `render.yaml` ships `runtime: docker`, `healthCheckPath: /api/health`, needs `standard` plan or above for memory
- **Railway**: `railway.toml` auto-builds the Dockerfile; set `CORS_ORIGIN` to the Pages domain
- **Fly**: `fly launch` with `fly.toml` (2GB VM), `force_https=true`

In production, tighten `CORS_ORIGIN` from `*` to `https://<user>.github.io`.
