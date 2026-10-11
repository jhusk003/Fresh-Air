from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_activities import (
        generate_mission_activity,
        validate_mission_activity,
    )


@workflow.defn
class MoodDividendWorkflow:
    @workflow.run
    async def run(self, preferences: dict) -> dict:
        mission = await workflow.execute_activity(
            generate_mission_activity,
            preferences,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=2),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
        validated = await workflow.execute_activity(
            validate_mission_activity,
            mission,
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_attempts=2,
            ),
        )
        return {"mission": validated, "used_ai": True}
