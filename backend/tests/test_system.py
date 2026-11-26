import os, sys, tempfile
os.environ["NEXUS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient
from app import system
from app.main import app

LAPTOP = system.Hardware("AMD Ryzen 5 5600H", 12, 8.0, "NVIDIA GeForce GTX 1650", 4.0, "nvidia", "Windows")
NOGPU = system.Hardware("x", 4, 8.0, None, 0.0, None, "Windows")
BIG = system.Hardware("x", 16, 32.0, "RTX 4090", 24.0, "nvidia", "Windows")
c = TestClient(app)

def test_parse_nvidia():
    assert system.parse_nvidia_smi("NVIDIA GeForce GTX 1650, 4096\n") == ("NVIDIA GeForce GTX 1650", 4.0)
    assert system.parse_nvidia_smi("") == (None, 0.0)
    assert system.parse_nvidia_smi("A, 2048\nB, 8192")[0] == "B"

def test_rating_for_benjamins_laptop():
    r = lambda gb: system.rate(gb, LAPTOP)["level"]
    assert r(1.0) == "green" and r(1.9) == "green"    # 3B
    assert r(2.9) == "green" or r(2.9) == "yellow"
    assert r(2.5) == "yellow"                         # 4B deler seg med skrivebordet
    assert r(4.7) == "red"                            # 7-8B sprenger 8 GB RAM
    assert r(9.0) == "red" and r(20) == "red"         # 14B+

def test_rating_other_machines():
    assert system.rate(9.0, BIG)["level"] == "green"
    assert system.rate(1.0, NOGPU)["level"] == "green"
    assert system.rate(4.7, NOGPU)["level"] == "red"

def test_est_size():
    assert 1.0 < system.est_size_from_params("1.5b") < 1.6
    assert system.est_size_from_params("270m") < 0.5
    assert system.est_size_from_params("cloud") is None

def test_pick():
    tags = {"fam1": [{"tag": "fam1:1b", "size_gb": 0.8}, {"tag": "fam1:3b", "size_gb": 1.9}, {"tag": "fam1:8b", "size_gb": 4.7},
                     {"tag": "fam1:3b-q8", "size_gb": 3.0}],
            "fam2": [{"tag": "fam2:2b", "size_gb": 1.4}]}
    best = system.pick(tags, LAPTOP)
    assert best["tag"] == "fam1:3b" and best["level"] == "green"
    assert system.pick({"f": [{"tag": "f:14b", "size_gb": 9.0}]}, LAPTOP) is None

def test_endpoints():
    h = c.get("/api/system").json()
    assert h["ram_gb"] > 0 and h["cores"] > 0
    assert c.get("/api/system/rate", params={"size_gb": 1.0}).json()["level"] in ("green", "yellow", "red")
    r = c.get("/api/recommendations").json()
    assert r["ok"] and len(r["topics"]) == 5
    print([(t["id"], t["model"] and (t["model"]["tag"], t["model"]["level"])) for t in r["topics"]])

def test_benchmark():
    r = c.post("/api/benchmark", json={"model": os.environ.get("TEST_MODEL", "mock:1b")}).json()
    assert r["tps"] > 0
    assert os.environ.get("TEST_MODEL", "mock:1b") in c.get("/api/benchmark").json()

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("OK", n)


def test_calibration_uses_measured_speed():
    system.set_calibration({}, LAPTOP)
    assert system.rate(1.9, LAPTOP)["basis"] == "estimate"
    # måling: 3B-modell (1.9 GB) gir 40 tok/s => K = 76
    system.set_calibration({"a:3b": {"tps": 40, "size_gb": 1.9}}, LAPTOP)
    r = system.rate(1.9, LAPTOP, "a:3b")
    assert r["basis"] == "measured" and r["level"] == "green" and r["tps"] == 40
    small = system.rate(0.8, LAPTOP)           # estimert raskere enn målt modell
    assert small["basis"] == "predicted" and small["tps"] > 40
    # for stor for minnet forblir rød selv om K er høy
    assert system.rate(20, LAPTOP)["level"] == "red"
    # treg maskin: 3B gir 3 tok/s => rød selv om den "passer"
    system.set_calibration({"a:3b": {"tps": 3, "size_gb": 1.9}}, LAPTOP)
    assert system.rate(1.9, LAPTOP, "a:3b")["level"] == "red"
    assert system.rate(0.8, LAPTOP)["level"] in ("yellow", "green")
    system.set_calibration({}, LAPTOP)


def test_spilled_model_prediction_slower():
    system.set_calibration({"a:3b": {"tps": 40, "size_gb": 1.9}}, LAPTOP)
    fit = system.rate(1.9, LAPTOP)["tps"]
    spill = system.rate(2.5, LAPTOP)           # 4B: deles mellom GPU og RAM
    assert spill["basis"] == "predicted" and spill["tps"] < fit / 2
    system.set_calibration({}, LAPTOP)
