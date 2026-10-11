import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from temporal_activities import (
    generate_mission_activity,
    validate_mission_activity,
)
from temporal_workflow import MoodDividendWorkflow


async def main():
    client = await Client.connect("localhost:7233")
    worker = Worker(
        client,
        task_queue="mood-dividend-queue",
        workflows=[MoodDividendWorkflow],
        activities=[
            generate_mission_activity,
            validate_mission_activity,
        ],
    )
    print("Mood Dividend Temporal worker is running.")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
