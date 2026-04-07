Smart Insulin Storage Monitor
Architecture
simulator.py          ← PI controller + thermal model (background thread)
dashboard.py          ← Streamlit live dashboard (reads shared state)
requirements.txt      ← Dependencies
How it works:

InsulinSimulator runs in a daemon thread, computing a new tick every second
The Streamlit dashboard reads directly from shared memory (deque) — no file I/O
streamlit-autorefresh triggers a UI rerender every 1 second
All controller parameters (target temp, Kp, Ki, ambient base) are adjustable live from the sidebar


Setup
bash# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the dashboard
streamlit run dashboard.py
Open your browser at http://localhost:8501

Improvements over the original MATLAB version
FeatureMATLAB originalThis versionSimulation speedpause(1) loop (real-time only)Background thread, 1s ticksData pipelineWrites CSV each tickShared in-memory dequeDashboard refreshPolls CSV every 5sst_autorefresh every 1sControllerPI (no anti-windup)PI with anti-windup clampLive parameter tuningNot possibleSidebar sliders, instant effectLanguage splitMATLAB + PythonPure PythonMLLinear regression (trains on sim's own output)Removed — replaced with real status logic

Key parameters (adjustable in sidebar)
ParameterDefaultEffectTarget temp5.0°CSet point for PI controllerKp1.2Proportional gain — higher = stronger response, less stableKi0.05Integral gain — corrects steady-state errorAmbient base28°CBase room temperature (sinusoidal variation + noise added)
