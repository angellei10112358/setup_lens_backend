# setup-lens-backend — Linux Docker, python:3.8 + PyAutoLens 2021.10.14.1 strong lock
# Do NOT use alpine (musl breaks numba/llvmlite/scipy). Use slim-bullseye (glibc, manylinux2014).
FROM python:3.8-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# System deps for scipy/matplotlib/astropy/h5py build + runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gfortran pkg-config \
    libopenblas-dev liblapack-dev \
    libcfitsio-dev libhdf5-dev libffi-dev \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer cache: requirements first
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade "pip==20.2.4" && \
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn || \
    pip install -r requirements.txt

COPY app/ ./app/

# Non-root (parity with BuildYourOwnGames/backend pattern)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
