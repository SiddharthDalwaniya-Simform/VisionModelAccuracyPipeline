# ============================================================
# CONFIG.PY — Dynamic environment loader
# ============================================================
#
# This file auto-loads the correct environment config based on:
#   1. The --env CLI flag      (e.g. python run.py --env stage)
#   2. The ENV environment var (e.g. set ENV=stage && python run.py)
#   3. Defaults to "dev" if neither is set.
#
# Environment configs live in  envs/<name>.py  (dev.py, stage.py, prod.py).
# Shared defaults live in      envs/base.py.
#
# All other modules keep using `import config` — no changes needed.
# ============================================================

import importlib
import os
import sys

VALID_ENVS = ("dev", "stage", "prod")

ENV = os.environ.get("ENV", "dev").lower()

if ENV not in VALID_ENVS:
    print(f"ERROR: Unknown environment '{ENV}'. Valid options: {', '.join(VALID_ENVS)}")
    sys.exit(1)

_env_module = importlib.import_module(f"envs.{ENV}")

# Expose every uppercase attribute from the env module at this module's top level,
# so `config.DB_HOST`, `config.POLL_INTERVAL`, etc. keep working everywhere.
_self = sys.modules[__name__]
for _attr in dir(_env_module):
    if _attr.isupper():
        setattr(_self, _attr, getattr(_env_module, _attr))
