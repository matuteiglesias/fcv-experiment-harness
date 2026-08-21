import pandas as pd

from fcv_harness.lattice_diagnostics import derive_country_iso3


# The recovered archive contains multiple legacy GADM naming generations.
# Both forms must produce the same transparent ISO3-like country identity.
values = pd.Series([
    "AGO.1.1_1",   # dotted legacy form
    "GHA1.1_2",    # GADM-v2-style Ghana form found in the real DHSGC lattice
    "GHA14.18_2",
    "KEN.12.3_1",
    "not_a_gid",   # do not infer arbitrary alphabetic labels
])
resolved = derive_country_iso3(values)

assert resolved.iloc[0] == "AGO"
assert resolved.iloc[1] == "GHA"
assert resolved.iloc[2] == "GHA"
assert resolved.iloc[3] == "KEN"
assert pd.isna(resolved.iloc[4])

print("COUNTRY IDENTITY TEST PASSED")
