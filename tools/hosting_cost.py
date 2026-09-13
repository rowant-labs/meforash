#!/usr/bin/env python3
"""Estimate GPU hosting cost from a provider's measured billable hours."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Sequence


@dataclass(frozen=True)
class CostEstimate:
    billed_gpu_hours: Decimal
    gpu_hour_rate_usd: Decimal
    completed_questions: int
    total_gpu_cost_usd: Decimal
    cost_per_1000_questions_usd: Decimal
    monthly_questions: int
    estimated_monthly_billed_gpu_hours: Decimal
    estimated_monthly_gpu_cost_usd: Decimal


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite nonnegative number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a finite nonnegative number") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return number


def _question_count(value: object, name: str, *, positive: bool) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be {'a positive' if positive else 'a nonnegative'} integer")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"{name} must be {'a positive' if positive else 'a nonnegative'} integer"
        ) from exc
    if not number.is_finite():
        raise ValueError(
            f"{name} must be {'a positive' if positive else 'a nonnegative'} integer"
        )
    valid_sign = number > 0 if positive else number >= 0
    if not valid_sign or number != number.to_integral_value():
        raise ValueError(
            f"{name} must be {'a positive' if positive else 'a nonnegative'} integer"
        )
    return int(number)


def calculate_costs(
    billed_gpu_hours: object,
    gpu_hour_rate_usd: object,
    completed_questions: object,
    monthly_questions: object,
) -> CostEstimate:
    """Calculate measured and projected GPU-only costs.

    ``billed_gpu_hours`` should be read from the hosting provider's billing meter.
    ``completed_questions`` must be positive because it is the denominator for the
    observed per-question rate.
    """

    hours = _decimal(billed_gpu_hours, "billed GPU hours")
    rate = _decimal(gpu_hour_rate_usd, "GPU-hour rate")
    completed = _question_count(completed_questions, "completed questions", positive=True)
    monthly = _question_count(monthly_questions, "monthly questions", positive=False)

    total = hours * rate
    hours_per_question = hours / Decimal(completed)
    monthly_hours = hours_per_question * Decimal(monthly)
    return CostEstimate(
        billed_gpu_hours=hours,
        gpu_hour_rate_usd=rate,
        completed_questions=completed,
        total_gpu_cost_usd=total,
        cost_per_1000_questions_usd=(total / Decimal(completed)) * Decimal(1000),
        monthly_questions=monthly,
        estimated_monthly_billed_gpu_hours=monthly_hours,
        estimated_monthly_gpu_cost_usd=monthly_hours * rate,
    )


def _format_number(value: Decimal, places: int = 6) -> str:
    quantum = Decimal(1).scaleb(-places)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    whole, _, fraction = f"{rounded:,.{places}f}".partition(".")
    fraction = fraction.rstrip("0")
    return whole if not fraction else f"{whole}.{fraction}"


def _format_usd(value: Decimal) -> str:
    text = _format_number(value)
    if "." not in text:
        text += ".00"
    elif len(text.rsplit(".", 1)[1]) == 1:
        text += "0"
    return f"${text}"


def format_estimate(estimate: CostEstimate) -> str:
    lines = [
        "GPU hosting cost estimate",
        f"Billed GPU hours: {_format_number(estimate.billed_gpu_hours)}",
        f"GPU-hour rate: {_format_usd(estimate.gpu_hour_rate_usd)}",
        f"Completed questions: {estimate.completed_questions:,}",
        f"Measured GPU cost: {_format_usd(estimate.total_gpu_cost_usd)}",
        (
            "Measured cost per 1,000 questions: "
            f"{_format_usd(estimate.cost_per_1000_questions_usd)}"
        ),
        f"Monthly question volume: {estimate.monthly_questions:,}",
        (
            "Estimated monthly billed GPU hours: "
            f"{_format_number(estimate.estimated_monthly_billed_gpu_hours)}"
        ),
        (
            "Estimated monthly GPU cost: "
            f"{_format_usd(estimate.estimated_monthly_gpu_cost_usd)}"
        ),
        "",
        "GPU costs only. Use billable GPU hours from the hosting provider; they include "
        "initialization and idle time.",
        "Do not sum overlapping request durations to estimate billed GPU hours.",
        "Monthly projections assume similar answer lengths, traffic clustering, and cold-start frequency.",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--billed-gpu-hours",
        required=True,
        help="Provider-reported billable GPU hours, including initialization and idle time",
    )
    parser.add_argument(
        "--gpu-hour-rate",
        "--per-gpu-hour-rate",
        dest="gpu_hour_rate",
        required=True,
        help="Price in USD per billed GPU hour",
    )
    parser.add_argument(
        "--completed-questions",
        required=True,
        help="Positive number of completed questions measured during those billed hours",
    )
    parser.add_argument(
        "--monthly-questions",
        required=True,
        help="Nonnegative monthly question volume to project",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        estimate = calculate_costs(
            args.billed_gpu_hours,
            args.gpu_hour_rate,
            args.completed_questions,
            args.monthly_questions,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(format_estimate(estimate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
