from datetime import date

from work.pilot_scenarios import (
    EXPECTED_SCENARIO_COUNTS,
    ScenarioKind,
    build_pilot_scenario,
    scenario_counts,
    shift_workdays,
)


TODAY = date(2026, 7, 13)


def is_working_day(day: date) -> bool:
    return day.weekday() < 5


def test_scenario_catalog_has_the_retained_distribution_and_workloads() -> None:
    scenarios = [
        build_pilot_scenario(index, today=TODAY, is_working_day=is_working_day)
        for index in range(73)
    ]

    assert scenario_counts() == EXPECTED_SCENARIO_COUNTS
    assert sum(item.workload <= 10 for item in scenarios) == 65
    assert sum(12 <= item.workload <= 20 for item in scenarios) == 8
    assert all(2 <= len(item.milestones) <= 6 for item in scenarios)


def test_scenario_dates_and_histories_are_calendar_coherent() -> None:
    scenarios = [
        build_pilot_scenario(index, today=TODAY, is_working_day=is_working_day)
        for index in range(73)
    ]

    for scenario in scenarios:
        assert (
            shift_workdays(
                scenario.start_date,
                int(scenario.workload.to_integral_value(rounding="ROUND_CEILING")),
                is_working_day,
            )
            == scenario.due_date
        )
        days = [item.day for item in scenario.milestones]
        assert days == sorted(set(days))
        assert scenario.start_date <= days[0] <= days[-1] <= TODAY
        assert all(0 < item.percentage <= 100 for item in scenario.milestones)
        assert all(item.percentage % 5 == 0 for item in scenario.milestones)

    completed = {
        ScenarioKind.ON_TIME,
        ScenarioKind.EARLY_COMPLETED,
        ScenarioKind.SLIGHT_LATE_COMPLETED,
        ScenarioKind.REOPENED_COMPLETED,
        ScenarioKind.BIG_LATE_COMPLETED,
    }
    for scenario in scenarios:
        if scenario.kind in completed:
            assert scenario.completion_date is not None
            assert scenario.milestones[-1].percentage == 100
        elif scenario.kind != ScenarioKind.CLOSED_EARLY:
            assert scenario.completion_date is None
            assert scenario.milestones[-1].percentage < 100


def test_only_two_scenarios_exceed_one_working_week_of_delay() -> None:
    scenarios = [
        build_pilot_scenario(index, today=TODAY, is_working_day=is_working_day)
        for index in range(73)
    ]
    large_delays = []
    for scenario in scenarios:
        end = scenario.completion_date or TODAY
        if end > scenario.due_date:
            delay = 0
            cursor = scenario.due_date
            while cursor < end:
                cursor = shift_workdays(cursor, 1, is_working_day)
                delay += 1
            if delay > 5:
                large_delays.append(scenario)

    assert [item.kind for item in large_delays] == [
        ScenarioKind.BIG_LATE_COMPLETED,
        ScenarioKind.BIG_LATE_ACTIVE,
    ]
    assert large_delays[0].milestones[-1].percentage == 100
