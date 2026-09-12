# setup-lens-backend

Linux Docker 后端，原样复用 `adhoc_jobs/lensing_gui/app.py:66-180` 物理（**不重写 PyAutoLens**），供纯静态前端调用。

- Base: `python:3.8-slim-bullseye`（glibc），强锁 `autolens==2021.10.14.1` + `numpy==1.20.2`（见 `requirements.txt`）
- `matplotlib Agg` 无头渲染，`scipy.fftconvolve` 卷积 Beam
- Critical/caustic 与成像同 `tracer+grid`（同系统），`PA=90+PA`（东=-x 左，符号已修正）

## 本地运行（Windows 验证用 .venv，Linux 用 Docker）

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

  - `png_base64` 为 `Blues` 无坐标轴 PNG（`origin="upper"`，行0=y_max），前端按 `extent=[x0,x1,y0,y1]` 拉伸
  - `critical_curves`/`caustics` 为世界坐标 `(y,x)` 折线，前端 `plot(x,y)` 即可
  - `high_res:true→300@0.02, false→150@0.04`（同视场 ±3"，拖动不抖）

## 部署

- **Render**: `render.yaml` 已配 `runtime: docker`，`healthCheckPath: /api/health`，需 `standard` 以上内存
- **Railway**: `railway.toml` 自动 Dockerfile 构建，设 `CORS_ORIGIN` 为 Pages 域名
- **Fly**: `fly launch` 用 `fly.toml`（2GB VM），`force_https=true`

生产务必将 `CORS_ORIGIN` 由 `*` 收紧为 `https://<user>.github.io`。
