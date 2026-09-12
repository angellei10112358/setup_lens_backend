"""Local smoke test — run with project .venv (Windows) or Docker Linux.
G:\\OpenCode\\context-infrastructure\\.venv\\Scripts\\python.exe test_api.py
"""
import sys
sys.path.insert(0, r"G:\OpenCode\context-infrastructure\adhoc_jobs\setup_lens_backend")
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
print("health:", c.get("/api/health").json())

payload = {
    "params": {"lens_e_y": -0.137, "lens_e_x": -0.265, "einstein_radius": 0.645, "slope": 1.895,
               "shear_e_y": 0.033, "shear_e_x": -0.055, "source_centre_y": -0.05, "source_centre_x": 0.08,
               "source_e_y": 0.001, "source_e_x": 0.001, "intensity": 1.7, "effective_radius": 0.063,
               "sersic_index": 0.639, "redshift_l": 1.7, "redshift_s": 2.5579},
    "high_res": False, "bmaj": 0.15, "bmin": 0.10, "pa": 30.0,
    "apply_beam": False, "with_critical": True, "with_caustics": True,
}
r = c.post("/api/compute", json=payload)
print("compute:", r.status_code)
j = r.json()
print(" image max", round(j["image"]["max"], 3), "extent", j["image"]["extent"])
print(" cc", len(j["critical_curves"]), "ca", len(j["caustics"]), "png", len(j["image"]["png_base64"]))
assert r.status_code == 200 and j["image"]["max"] > 0
print("OK")
