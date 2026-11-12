"""Entry point for Streamlit Community Cloud (it looks for this file by default).
Locally you can also run:   streamlit run streamlit_app.py   or   python -m cpcalc ui"""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cpcalc", "app.py"), run_name="__main__")
