from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))

from synthetic_demo import make_demo
from fcv_harness import build_exposure_state, spatial_did, run_gates

obs, projects, links, spec = make_demo(n=700)
df = build_exposure_state(obs, projects, links, spec.radius_km)
assert set(df.exposure_state.unique()).issubset({"never", "planned", "active", "completed", "ambiguous"})

est = spatial_did(df, spec.outcome, spec.covariates, spec.fixed_effects)
assert est["ok"]

gates = run_gates(obs, projects, links, spec)
assert len(gates) >= 6
assert gates[0].status == "GREEN"

print("SMOKE TEST PASSED")
print("effect:", round(est["effect_completed_minus_planned"], 4))
print("gates:", [(g.gate, g.status) for g in gates])
