import unittest
from concurrent.futures import ThreadPoolExecutor
from bibleprep.warmup_gate import WarmupGate


class WarmupGateTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.gate = WarmupGate(clock=lambda: self.now)

    def test_concurrent_visitors_share_one_wake(self):
        with ThreadPoolExecutor(max_workers=10) as pool:
            tickets = list(pool.map(lambda _: self.gate.begin(eligible=True), range(30)))
        self.assertEqual(sum(t is not None for t in tickets), 1)
        self.assertEqual(self.gate.status()['phase'], 'warming')

    def test_ineligible_and_polling_never_start_work(self):
        self.assertIsNone(self.gate.begin())
        for _ in range(20):
            self.assertEqual(self.gate.status()['phase'], 'asleep')
        self.assertEqual(len(self.gate.starts), 0)

    def test_uncertain_timeout_blocks_retry_until_reconciled(self):
        ticket = self.gate.begin(eligible=True)
        self.now = 4000
        self.assertEqual(self.gate.status()['phase'], 'unknown')
        self.assertIsNone(self.gate.begin(eligible=True))
        self.assertTrue(self.gate.reconcile(ticket, phase='asleep', observed_at=self.now))
        self.assertIsNotNone(self.gate.begin(eligible=True))

    def test_old_callback_cannot_override_new_wake(self):
        old = self.gate.begin(eligible=True)
        self.gate.reconcile(old, phase='asleep', observed_at=self.now)
        new = self.gate.begin(eligible=True)
        self.assertNotEqual(old, new)
        self.assertFalse(self.gate.reconcile(old, phase='ready', observed_at=self.now))
        self.assertEqual(self.gate.status()['phase'], 'warming')

    def test_polling_does_not_extend_readiness(self):
        ticket = self.gate.begin(eligible=True)
        self.gate.reconcile(ticket, phase='ready', observed_at=self.now)
        self.now = 14
        self.assertEqual(self.gate.status()['phase'], 'ready')
        self.now = 15
        self.assertEqual(self.gate.status()['phase'], 'unknown')
        self.assertIsNone(self.gate.begin(eligible=True))

    def test_repeated_failures_consume_wake_allowance(self):
        for _ in range(2):
            ticket = self.gate.begin(eligible=True)
            self.assertIsNotNone(ticket)
            self.gate.reconcile(ticket, phase='asleep', observed_at=self.now)
        self.assertIsNone(self.gate.begin(eligible=True))
        self.now = 3600
        self.assertIsNotNone(self.gate.begin(eligible=True))

    def test_delayed_same_ticket_observations_cannot_revive_readiness(self):
        ticket = self.gate.begin(eligible=True)
        self.now = 2
        self.assertTrue(self.gate.reconcile(ticket, phase='ready', observed_at=2))
        self.now = 3
        self.assertFalse(self.gate.reconcile(ticket, phase='unknown', observed_at=1))
        self.now = 20
        self.assertFalse(self.gate.reconcile(ticket, phase='ready', observed_at=2))
        self.assertEqual(self.gate.status()['phase'], 'unknown')

    def test_late_first_observation_does_not_get_new_readiness_ttl(self):
        ticket = self.gate.begin(eligible=True)
        self.now = 50
        self.assertTrue(self.gate.reconcile(ticket, phase='ready', observed_at=1))
        self.assertEqual(self.gate.status()['phase'], 'unknown')

    def test_status_does_not_disclose_private_ticket(self):
        self.gate.begin(eligible=True)
        self.assertEqual(set(self.gate.status()), {'phase', 'elapsed_seconds'})


if __name__ == '__main__':
    unittest.main()
