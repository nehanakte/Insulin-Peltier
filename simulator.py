"""
simulator.py — Insulin Storage Monitor: Background Simulation Engine
Runs in a daemon thread, pushes data into a shared deque. No CSV, no MATLAB.
"""

import threading
import time
import math
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimState:
    time: int = 0
    chamber_temp: float = 3.5
    ambient_temp: float = 28.0
    battery: float = 100.0
    cooling_output: float = 0.0
    pi_error: float = 0.0
    integral_error: float = 0.0
    status: str = "safe"          # "safe" | "warning" | "danger"
    status_msg: str = "System nominal"


@dataclass
class SimConfig:
    target_temp: float = 5.0
    kp: float = 1.2
    ki: float = 0.05
    ambient_base: float = 28.0
    k1: float = 0.02             # heat leakage coefficient
    k2: float = 0.35             # cooling strength coefficient
    integral_limit: float = 50.0  # anti-windup clamp
    tick_interval: float = 1.0   # seconds between ticks


class InsulinSimulator:
    """
    PI-controlled Peltier cooling simulation.
    Thread-safe: read `history` and `latest` from any thread.
    """

    def __init__(self, config: Optional[SimConfig] = None, history_len: int = 120):
        self.config = config or SimConfig()
        self.history: deque[SimState] = deque(maxlen=history_len)
        self.latest = SimState()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Mutable controller state (reset on restart)
        self._t = 0
        self._T = 3.5
        self._B = 100.0
        self._integral = 0.0

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def start(self):
        """Start background simulation thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop background thread gracefully."""
        self._stop_event.set()

    def reset(self):
        """Reset simulation state."""
        self.stop()
        with self._lock:
            self._t = 0
            self._T = 3.5
            self._B = 100.0
            self._integral = 0.0
            self.history.clear()
            self.latest = SimState()
        self.start()

    def update_config(self, **kwargs):
        """Live-update config (target_temp, kp, ki, ambient_base …)."""
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, float(v))

    def get_history_lists(self):
        """Return history as separate lists — safe to call from Streamlit."""
        with self._lock:
            snap = list(self.history)
        keys = ["time", "chamber_temp", "ambient_temp",
                "battery", "cooling_output", "pi_error"]
        return {k: [getattr(s, k) for s in snap] for k in keys}

    # ------------------------------------------------------------------ #
    #  Internal simulation loop                                            #
    # ------------------------------------------------------------------ #

    def _run(self):
        while not self._stop_event.is_set():
            self._tick()
            time.sleep(self.config.tick_interval)

    def _tick(self):
        cfg = self.config
        self._t += 1
        t = self._t

        # --- Ambient temperature ---
        noise = 1.2 * random.gauss(0, 1)
        spike = 3.0 * random.random() if random.random() < 0.05 else 0.0
        T_room = cfg.ambient_base + 6 * math.sin(0.02 * t) + noise + spike

        # --- Battery drain ---
        self._B = max(0.0, self._B - 0.06 + 0.01 * random.gauss(0, 1))

        # --- PI controller (with anti-windup) ---
        error = self._T - cfg.target_temp
        self._integral = max(
            -cfg.integral_limit,
            min(cfg.integral_limit, self._integral + error)
        )
        efficiency = 0.85 + 0.30 * random.random()
        cooling = (cfg.kp * error + cfg.ki * self._integral) \
                  * cfg.k2 * efficiency * (self._B / 100.0)
        cooling = max(0.0, cooling)

        # --- Thermal dynamics ---
        heat = cfg.k1 * (T_room - self._T) + 0.15 * random.gauss(0, 1)
        self._T += heat - cooling
        self._T = max(1.5, min(9.0, self._T))  # physical bounds

        # --- Status classification ---
        if self._T > 8.0:
            status, msg = "danger", f"DANGER — overheating ({self._T:.2f}°C). Insulin at risk!"
        elif self._T < 2.0:
            status, msg = "warning", f"WARNING — freezing risk ({self._T:.2f}°C). Insulin may crystallize."
        elif self._B < 15.0:
            status, msg = "warning", f"LOW BATTERY — {self._B:.1f}% remaining."
        else:
            status, msg = "safe", f"Nominal — chamber {self._T:.2f}°C, target {cfg.target_temp:.1f}°C."

        state = SimState(
            time=t,
            chamber_temp=round(self._T, 3),
            ambient_temp=round(T_room, 2),
            battery=round(self._B, 2),
            cooling_output=round(cooling, 4),
            pi_error=round(error, 3),
            integral_error=round(self._integral, 3),
            status=status,
            status_msg=msg,
        )

        with self._lock:
            self.history.append(state)
            self.latest = state
