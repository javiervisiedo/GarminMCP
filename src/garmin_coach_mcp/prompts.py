"""MCP Coaching Prompts for Garmin Coach MCP."""

from __future__ import annotations

from datetime import date


def morning_readiness_check(target_date: str | None = None) -> str:
    """Generate a structured morning readiness check-in prompt for the AI Coach.

    Instructs the assistant to invoke `get_coach_daily_briefing` (and optionally
    `get_sleep_and_recovery` if deeper sleep context is needed), evaluate Training
    Readiness, Body Battery, HRV vs. baseline, RHR, and yesterday's training load,
    and output a structured daily readiness verdict with today's workout adjustment.
    """
    resolved_date = (target_date or "").strip() or date.today().isoformat()
    return (
        f"Act as my Elite Personal Endurance & Physiology Coach performing a Morning Readiness Check for `{resolved_date}`.\n\n"
        "### Step 1: Gather Telemetry\n"
        f"1. Call `get_coach_daily_briefing(target_date=\"{resolved_date}\")` to retrieve my Training Readiness, "
        "Body Battery (current, charged, drained), overnight Sleep score & stages, HRV status vs. baseline, "
        "Resting Heart Rate (vs. 7-day average), Stress, and yesterday's completed workouts.\n"
        "2. If my sleep score is below 70 or my HRV is unbalanced/low, also call "
        f"`get_sleep_and_recovery(end_date=\"{resolved_date}\")` to inspect my 7-day recovery trajectory.\n\n"
        "### Step 2: Deliver Structured Coaching Verdict\n"
        "Provide a concise, evidence-backed coaching briefing with these exact sections:\n"
        "1. **Readiness Score & Traffic-Light Verdict**: State my readiness score (/100), Body Battery level, "
        "and overall status (`GREEN — Go for Quality`, `YELLOW — Modify/Steady`, or `RED — Active Recovery/Rest`).\n"
        "2. **Autonomic & Sleep Bottlenecks**: Highlight the primary limiters or strengths across overnight HRV "
        "(last night vs. personal baseline), RHR delta vs. 7-day average, and deep/REM sleep architecture.\n"
        "3. **Today's Workout Prescription & Adjustment**: Recommend the optimal training intensity "
        "(`high_intensity`, `moderate_steady`, `easy_recovery`, or `rest`), specific HR/pace/power zone caps, "
        "and how to modify my planned session based on yesterday's training load and remaining recovery time."
    )


def post_workout_debrief(activity_id: str | None = None) -> str:
    """Generate a structured post-workout execution debrief prompt for the AI Coach.

    Takes an optional `activity_id` (or instructs the assistant to find the latest
    activity via `list_recent_activities(limit=1)`), calls `get_activity_details`
    and `get_training_status_and_load`, and evaluates pacing evenness, cardiac drift,
    interval execution, and HR/power/pace zone compliance.
    """
    clean_id = (str(activity_id).strip() if activity_id is not None else "") or None
    if clean_id:
        id_instruction = (
            f"1. Call `get_activity_details(activity_id=\"{clean_id}\")` to inspect the full lap splits, "
            "HR/power/pace zone distributions, elevation, cadence, weather, and cardiac drift."
        )
    else:
        id_instruction = (
            "1. Call `list_recent_activities(limit=1)` to identify my most recently completed workout, "
            "then call `get_activity_details(activity_id=...)` on that `activity_id`."
        )

    return (
        "Act as my Elite Endurance Coach and Sports Physiologist conducting a Post-Workout Debrief.\n\n"
        "### Step 1: Retrieve Workout & Load Telemetry\n"
        f"{id_instruction}\n"
        "2. Call `get_training_status_and_load()` to evaluate how this session impacted my Acute Load, "
        "Chronic Load, ACWR load ratio, aerobic/anaerobic Training Effect, and recovery time remaining.\n\n"
        "### Step 2: Analyze Workout Execution\n"
        "Deliver a structured debrief covering:\n"
        "1. **Session Snapshot & Stimulus**: Summarize distance, duration, average pace/power, average/max HR, "
        "and Aerobic vs. Anaerobic Training Effect (`primary_benefit`).\n"
        "2. **Pacing Discipline & Split Analysis**: Evaluate lap-by-lap pacing stability (negative split, even split, "
        "or positive fade) and consistency across work intervals vs. recovery bouts.\n"
        "3. **Cardiac Drift & Aerobic Decoupling**: Interpret the reported `cardiac_drift_pct` in context of "
        "session duration, elevation, and weather conditions (temperature/humidity). Flag if drift exceeded 5%.\n"
        "4. **Zone Compliance**: Audit time spent in Heart Rate and Power/Pace zones against the intended session purpose "
        "(e.g., whether an easy day crept into Zone 3/4 or whether threshold intervals hit target zones).\n"
        "5. **Recovery Window & Next-Session Guidance**: State updated recovery hours, ACWR status, and recommended "
        "nutrition/recovery focus before the next quality session."
    )


def weekly_training_plan(
    goal: str = "Build aerobic threshold and 10K/Half-Marathon readiness",
    target_race_date: str | None = None,
) -> str:
    """Generate a periodized 7-day training plan prompt tailored to the athlete's goal and 28-day load.

    Instructs the assistant to analyze the last 28 days of health trends and training load
    (`get_health_trends(days=28)`, `list_recent_activities`, `get_training_status_and_load`),
    design a polarized/periodized 7-day schedule, and offer to generate structured workouts
    via `create_structured_workout_json`.
    """
    clean_goal = (goal or "").strip() or "Build aerobic threshold and 10K/Half-Marathon readiness"
    clean_race_date = (target_race_date or "").strip() or None
    race_clause = (
        f" (Target Race Date: `{clean_race_date}`)"
        if clean_race_date
        else " (No fixed race date — focus on progressive block periodization)"
    )

    return (
        f"Act as my Elite Periodization & Endurance Coach building a customized 7-Day Training Plan.\n"
        f"**Primary Goal**: {clean_goal}{race_clause}\n\n"
        "### Step 1: Audit 28-Day Load, Trends & Thresholds\n"
        "1. Call `get_health_trends(days=28)` to evaluate my 4-week rolling averages and deltas for RHR, "
        "overnight HRV, sleep duration, stress, average weekly training volume (hours & distance), and coach flags.\n"
        "2. Call `get_training_status_and_load()` to check my current VO2 Max, Acute Load, Chronic Load, "
        "ACWR load ratio, Low/High Aerobic vs. Anaerobic load focus, and Training Status.\n"
        "3. Call `list_recent_activities(limit=10)` to inspect my recent long runs/rides, key workouts, and sport mix.\n"
        "4. Optionally read `garmin://athlete/profile` or call `get_body_composition_and_biometrics()` to anchor "
        "my exact Heart Rate, Pace, and Power zones (LTHR, threshold pace, FTP).\n\n"
        "### Step 2: Synthesize Load Capacity & Periodization Phase\n"
        "- Determine whether the upcoming 7 days should be a **Progressive Build Week**, **Maintenance/Specificity Week**, "
        "or **Deload/Recovery Week** based on ACWR (target 0.8–1.3) and 28-day HRV/RHR trends.\n\n"
        "### Step 3: Output 7-Day Day-by-Day Training Plan\n"
        "Present a structured 7-day table and daily breakdown (Day 1 through Day 7) specifying for each day:\n"
        "- **Session Title & Sport Type** (`running`, `cycling`, `strength`, `rest`, etc.)\n"
        "- **Duration & Distance Target**\n"
        "- **Workout Structure**: Warmup, Main Set (intervals/tempo/endurance), and Cooldown with explicit "
        "Heart Rate / Pace / Power zone targets.\n"
        "- **Physiological Purpose**: Why this session fits the weekly microcycle.\n\n"
        "### Step 4: Structured Workout Export\n"
        "For the key quality sessions in the 7-day plan, call `create_structured_workout_json(...)` "
        "(with `upload_to_garmin=False` unless I explicitly ask to upload) to generate validated Garmin Connect "
        "workout JSON definitions ready to sync to my watch."
    )


import garmin_coach_mcp.server  # noqa: E402, F401
