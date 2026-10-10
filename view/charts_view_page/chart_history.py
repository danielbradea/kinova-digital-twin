"""Bounded telemetry history with continuous joint angles and gap handling."""
from collections import deque
import math
import numpy as np


class ChartHistory:
    def __init__(self, max_samples=2400, max_age=120, allow_duplicates=False):
        self.frames = deque(maxlen=max_samples)
        self.max_age = max_age
        self.allow_duplicates = allow_duplicates
        self.previous = None

    def clear(self):
        self.frames.clear()
        self.previous = None

    def append(self, frame):
        t = frame["time"].timestamp()
        if not math.isfinite(t) or (self.previous is not None and
                (t < self.previous["t"] or (t == self.previous["t"] and not self.allow_duplicates))):
            return
        result = {"t": t}
        gap = self.previous is None or t - self.previous["t"] > 1.
        for i, joint in enumerate(frame["joints"], 1):
            for field in ("position", "velocity", "torque", "current", "temperature"):
                value = joint.get(field)
                result[f"j{i}_{field}"] = float(value) if value is not None else float("nan")
            key = f"j{i}_position"
            angle = result[key]
            if gap or not math.isfinite(angle) or not math.isfinite(self.previous[key]):
                continuous = angle
            else:
                # Follow the shortest angle change across the 0/360-degree boundary.
                delta = (angle - self.previous[key] + 180) % 360 - 180
                continuous = self.previous[f"j{i}_continuous"] + delta
            result[f"j{i}_continuous"] = continuous
        for key, value in frame["base"].items():
            result[key] = float(value) if value is not None else float("nan")
        result["power"] = result.get("arm_voltage", float("nan")) * result.get("arm_current", float("nan"))
        self.frames.append(result)
        self.previous = result
        while self.max_age is not None and self.frames and t - self.frames[0]["t"] > self.max_age:
            self.frames.popleft()

    def window(self, seconds):
        if not self.frames:
            return []
        cutoff = self.frames[-1]["t"] - seconds
        return [frame for frame in self.frames if frame["t"] >= cutoff]


def curve_data(frames, key, xkey="t"):
    """Insert NaNs so neither time plots nor trajectories bridge missing samples."""
    x, y = [], []
    previous = None
    for frame in frames:
        if previous is not None and frame["t"] - previous > 1:
            x.append(float("nan"))
            y.append(float("nan"))
        x.append(frame.get(xkey, float("nan")))
        y.append(frame.get(key, float("nan")))
        previous = frame["t"]
    return np.asarray(x), np.asarray(y)
