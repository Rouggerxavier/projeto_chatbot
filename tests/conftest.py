import os
import sys

# Garante que o pacote local `app` seja importável durante os testes
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)