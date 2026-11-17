# backend/tests/conftest.py
import sys
import os

# Project root (red_thread) add to path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, root_dir)

# Backend folder added to path
backend_dir=os.path.join(root_dir,"backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
