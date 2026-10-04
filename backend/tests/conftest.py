"""Configuration pytest — rend `app` importable depuis la racine backend.

Les suites existantes s'exécutent depuis `backend/` ( sys.path.insert ).
Ce conftest permet de lancer `pytest` depuis n'importe où en ajoutant le
dossier backend au sys.path.
"""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
