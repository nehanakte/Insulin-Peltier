"""
dashboard.py — Insulin Storage Monitor: Live Streamlit Dashboard
Run with:  streamlit run dashboard.py

Architecture:
  - InsulinSimulator runs in a daemon thread (started once via st.session_state)
  - Dashboard reads shared state each rerun — no file I/O, no CSV
  - Streamlit auto-refreshes via st_autorefresh (1 s interval)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh

from simulator import InsulinSimulator, SimConfig

# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Insulin Monitor",
    page_icon="🧊",
    layout="wide",
)

# ──────────────────────────────────────────────
# Bootstrap simulator (once per session)
# ──────────────────────────────────────────────
if "sim" not in st.session_state:
    st.session_state.sim = InsulinSimulator(
        config=SimConfig(
            target_temp=5.0,
            kp=1.2,
            ki=0.05,
            ambient_base=28.0,
        )
    )
    st.session_state.sim.start()

sim: InsulinSimulator = st.session_state.sim

# ──────────────────────────────────────────────
# Auto-refresh every 1 second
# ──────────────────────────────────────────────
st_autorefresh(interval=1000, key="autorefresh")

# ──────────────────────────────────────────────
# Sidebar — live controls
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Controls")

    target = st.slider("Target temperature (°C)", 2.0, 8.0, sim.config.target_temp, 0.5)
    kp     = st.slider("Kp (proportional gain)",  0.5, 3.0, sim.config.kp, 0.1)
    ki     = st.slider("Ki (integral gain)",       0.01, 0.2, sim.config.ki, 0.01)
    amb    = st.slider("Ambient base (°C)",        20.0, 40.0, sim.config.ambient_base, 1.0)

    sim.update_config(target_temp=target, kp=kp, ki=ki, ambient_base=amb)

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("⏸ Pause" if not sim._stop_event.is_set() else "▶ Resume", use_container_width=True):
            if sim._stop_event.is_set():
                sim.start()
            else:
                sim.stop()
    with col_b:
        if st.button("↺ Reset", use_container_width=True):
            sim.reset()

    st.markdown("---")
    st.markdown("**System info**")
    st.caption(f"History window: {sim.history.maxlen} ticks")
    st.caption(f"Anti-windup limit: ±{sim.config.integral_limit}")
    st.caption(f"Heat leakage k1: {sim.config.k1}")
    st.caption(f"Cooling strength k2: {sim.config.k2}")

# ──────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────
latest = sim.latest
running_badge = "🟢 LIVE" if not sim._stop_event.is_set() else "🟡 PAUSED"

st.markdown(f"# 🧊 Smart Insulin Storage Monitor &nbsp; {running_badge}")
st.caption(f"t = {latest.time} min &nbsp;|&nbsp; PI controller with anti-windup &nbsp;|&nbsp; No CSV · No MATLAB · Pure Python")

# ──────────────────────────────────────────────
# Status banner
# ──────────────────────────────────────────────
status_colors = {"safe": "green", "warning": "orange", "danger": "red"}
status_icons  = {"safe": "✅", "warning": "⚠️", "danger": "🚨"}
color = status_colors.get(latest.status, "green")
icon  = status_icons.get(latest.status, "✅")

st.markdown(
    f"""
    <div style="
        padding: 12px 18px;
        border-radius: 8px;
        background: {'#e6f4ea' if color=='green' else '#fff3e0' if color=='orange' else '#fce8e6'};
        border-left: 4px solid {'#34a853' if color=='green' else '#fbbc04' if color=='orange' else '#ea4335'};
        color: {'#1e4620' if color=='green' else '#5f3b00' if color=='orange' else '#5c0000'};
        font-size: 14px;
        margin-bottom: 1rem;
    ">
        {icon} &nbsp; {latest.status_msg}
    </div>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# Metric cards
# ──────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

def temp_delta(val, target):
    d = round(val - target, 2)
    return f"{d:+.2f}°C from target"

c1.metric("🌡 Chamber temp",   f"{latest.chamber_temp:.2f}°C", temp_delta(latest.chamber_temp, sim.config.target_temp))
c2.metric("☀️ Ambient temp",   f"{latest.ambient_temp:.1f}°C")
c3.metric("❄️ Cooling output", f"{latest.cooling_output:.3f}")
c4.metric("🔋 Battery",        f"{latest.battery:.1f}%",
          delta=f"{(latest.battery - 100):.1f}% from full",
          delta_color="inverse")
c5.metric("📐 PI error",        f"{latest.pi_error:.3f}°C")

st.markdown("---")

# ──────────────────────────────────────────────
# Charts
# ──────────────────────────────────────────────
hist = sim.get_history_lists()

if len(hist["time"]) > 1:
    times = hist["time"]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "Chamber vs Ambient Temperature (°C)",
            "PI Controller Error (°C)",
            "Battery Level (%)",
            "Cooling Output",
        ),
        vertical_spacing=0.14,
        horizontal_spacing=0.08,
    )

    # Chamber + ambient
    fig.add_trace(go.Scatter(x=times, y=hist["chamber_temp"],
        name="Chamber", line=dict(color="#1967d2", width=2),
        fill="tozeroy", fillcolor="rgba(25,103,210,0.06)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=times, y=hist["ambient_temp"],
        name="Ambient", line=dict(color="#e37400", width=1.5, dash="dot")), row=1, col=1)

    # Target line
    fig.add_hline(y=sim.config.target_temp, line_dash="dash",
                  line_color="rgba(25,103,210,0.4)", row=1, col=1)
    fig.add_hline(y=8, line_dash="dot", line_color="rgba(220,0,0,0.4)", row=1, col=1)
    fig.add_hline(y=2, line_dash="dot", line_color="rgba(0,0,220,0.4)", row=1, col=1)

    # PI error
    fig.add_trace(go.Scatter(x=times, y=hist["pi_error"],
        name="Error", line=dict(color="#c5221f", width=1.5),
        fill="tozeroy", fillcolor="rgba(197,34,31,0.06)"), row=1, col=2)
    fig.add_hline(y=0, line_color="rgba(0,0,0,0.2)", row=1, col=2)

    # Battery
    fig.add_trace(go.Scatter(x=times, y=hist["battery"],
        name="Battery", line=dict(color="#188038", width=2),
        fill="tozeroy", fillcolor="rgba(24,128,56,0.08)"), row=2, col=1)

    # Cooling output
    fig.add_trace(go.Scatter(x=times, y=hist["cooling_output"],
        name="Cooling", line=dict(color="#9334e6", width=1.5),
        fill="tozeroy", fillcolor="rgba(147,52,230,0.06)"), row=2, col=2)

    fig.update_layout(
        height=480,
        showlegend=False,
        margin=dict(l=0, r=0, t=40, b=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(size=12),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0", tickfont=dict(size=10))
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0", tickfont=dict(size=10))

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Simulation starting… charts will appear after the first few ticks.")

# ──────────────────────────────────────────────
# Live log table
# ──────────────────────────────────────────────
with st.expander("📋 Live data log", expanded=False):
    if hist["time"]:
        df = pd.DataFrame(hist)
        df = df.iloc[::-1].reset_index(drop=True)   # newest first
        df.columns = ["Time (min)", "Chamber °C", "Ambient °C",
                      "Battery %", "Cooling", "PI Error"]
        st.dataframe(df.style.format(precision=2), use_container_width=True, height=250)
    else:
        st.caption("No data yet.")
