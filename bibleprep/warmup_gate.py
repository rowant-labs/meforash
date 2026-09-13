"""Offline prototype for coordinating one optional model wake operation.

Not wired into the beta or any provider. The caller must authenticate, check
quota/budget, dispatch at most one wake per ticket, and reconcile unknown work.
Polling this object never dispatches work or prolongs a provider's idle timer.
Use a shared durable implementation before running multiple gateway processes.
"""
from collections import deque
from threading import Lock
from time import monotonic
from uuid import uuid4


class WarmupGate:
    def __init__(self, *, clock=monotonic, max_starts=2, window=3600,
                 deadline=600, ready_ttl=15):
        if any(value <= 0 for value in (max_starts, window, deadline, ready_ttl)):
            raise ValueError('Limits must be positive')
        self.clock = clock
        self.max_starts = max_starts
        self.window = window
        self.deadline = deadline
        self.ready_ttl = ready_ttl
        self.lock = Lock()
        self.starts = deque()
        self.phase = 'asleep'
        self.ticket = None
        self.observed_at = None
        self.attempt_at = None
        self.changed_at = clock()

    def _refresh(self, now):
        while self.starts and self.starts[0] <= now - self.window:
            self.starts.popleft()
        if self.phase == 'warming' and now - self.changed_at >= self.deadline:
            # A timeout does not prove remote work stopped. Never auto-retry it.
            self.phase = 'unknown'
        if self.phase == 'ready' and now - self.changed_at >= self.ready_ttl:
            # Readiness expired, not evidence that the provider is now asleep.
            self.phase = 'unknown'

    def begin(self, *, eligible=False):
        """Return a private dispatch ticket once, or None; eligibility is external."""
        with self.lock:
            now = self.clock()
            self._refresh(now)
            if (not eligible or self.phase != 'asleep'
                    or len(self.starts) >= self.max_starts):
                return None
            self.ticket = uuid4().hex
            self.observed_at = None
            self.attempt_at = now
            self.starts.append(now)
            self.phase = 'warming'
            self.changed_at = now
            return self.ticket

    def reconcile(self, ticket, *, phase, observed_at):
        """Apply provider-observed state. 'asleep' requires verified no active wake.

        observed_at uses this gate's monotonic clock, captured before querying
        the provider; observations must be serialized or timestamped at dispatch.
        'ready' requires the intended model/adapter to be loaded. A network error
        is 'unknown', not 'asleep'. Dispatch tickets stay server-side.
        """
        if phase not in {'asleep', 'ready', 'unknown'}:
            raise ValueError('Invalid observed state')
        with self.lock:
            now = self.clock()
            if (ticket is None or ticket != self.ticket
                    or not isinstance(observed_at, (int, float))
                    or not self.attempt_at <= observed_at <= now
                    or (self.observed_at is not None
                        and observed_at <= self.observed_at)):
                return False
            self.observed_at = observed_at
            self.phase = phase
            self.changed_at = observed_at
            self._refresh(now)
            return True

    def status(self):
        with self.lock:
            now = self.clock()
            self._refresh(now)
            return {'phase': self.phase,
                    'elapsed_seconds': max(0, int(now - self.changed_at))
                    if self.phase == 'warming' else None}
