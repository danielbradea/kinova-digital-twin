from collections import deque
from view.live_reading_page.live_reading_worker import LiveReadingWorker


class ChartsWorker(LiveReadingWorker):
    """Retain samples between GUI refreshes, without an unbounded signal queue."""
    def __init__(self, config, parent=None):
        super().__init__(config, parent)
        self.pending = deque(maxlen=2400)

    def publish(self, joints, base):
        super().publish(joints, base)
        with self._lock:
            self.pending.append(self._latest)

    def drain(self):
        with self._lock:
            frames = list(self.pending)
            self.pending.clear()
        return frames
