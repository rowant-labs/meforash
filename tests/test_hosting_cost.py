import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal

from tools import hosting_cost


class HostingCostTests(unittest.TestCase):
    def test_calculates_measured_and_projected_gpu_costs(self):
        estimate = hosting_cost.calculate_costs("2.5", "1.20", 100, 10_000)

        self.assertEqual(estimate.total_gpu_cost_usd, Decimal("3.000"))
        self.assertEqual(estimate.cost_per_1000_questions_usd, Decimal("30.000"))
        self.assertEqual(estimate.estimated_monthly_billed_gpu_hours, Decimal("250.000"))
        self.assertEqual(estimate.estimated_monthly_gpu_cost_usd, Decimal("300.00000"))

    def test_zero_usage_and_zero_monthly_volume_are_valid(self):
        estimate = hosting_cost.calculate_costs(0, 0, 1, 0)

        self.assertEqual(estimate.total_gpu_cost_usd, Decimal(0))
        self.assertEqual(estimate.cost_per_1000_questions_usd, Decimal(0))
        self.assertEqual(estimate.estimated_monthly_gpu_cost_usd, Decimal(0))

    def test_rejects_nonfinite_and_negative_decimal_inputs(self):
        cases = [
            ("NaN", "1", 1, 1),
            ("Infinity", "1", 1, 1),
            ("-0.1", "1", 1, 1),
            ("1", "NaN", 1, 1),
            ("1", "Infinity", 1, 1),
            ("1", "-0.1", 1, 1),
        ]

        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                hosting_cost.calculate_costs(*arguments)

    def test_completed_questions_must_be_a_positive_integer(self):
        for value in (0, -1, "1.5", "NaN", True):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "completed questions must be a positive integer"
            ):
                hosting_cost.calculate_costs(1, 1, value, 100)

    def test_monthly_questions_must_be_a_nonnegative_integer(self):
        for value in (-1, "2.5", "Infinity", False):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "monthly questions must be a nonnegative integer"
            ):
                hosting_cost.calculate_costs(1, 1, 10, value)

    def test_cli_prints_costs_and_billable_hours_guidance(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = hosting_cost.main(
                [
                    "--billed-gpu-hours",
                    "2.5",
                    "--gpu-hour-rate",
                    "1.20",
                    "--completed-questions",
                    "100",
                    "--monthly-questions",
                    "10000",
                ]
            )

        rendered = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("Measured GPU cost: $3.00", rendered)
        self.assertIn("Measured cost per 1,000 questions: $30.00", rendered)
        self.assertIn("Estimated monthly GPU cost: $300.00", rendered)
        self.assertIn("initialization and idle time", rendered)
        self.assertIn("Do not sum overlapping request durations", rendered)

    def test_cli_reports_invalid_values_without_a_traceback(self):
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaisesRegex(SystemExit, "2"):
            hosting_cost.main(
                [
                    "--billed-gpu-hours",
                    "nan",
                    "--gpu-hour-rate",
                    "1",
                    "--completed-questions",
                    "10",
                    "--monthly-questions",
                    "100",
                ]
            )

        self.assertIn("billed GPU hours must be a finite nonnegative number", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
