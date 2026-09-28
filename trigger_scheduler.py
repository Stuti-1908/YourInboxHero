import asyncio
from src.scheduler import daily_sweep
from src.db import SessionLocal

async def test_scheduler():
    print("🚀 [TEST] Forcing the daily background scheduler to run right now...")
    await daily_sweep()
    print("✅ [TEST] Daily scheduler sweep complete! Check your GHL account / Phone for SMS or Voice triggers.")

if __name__ == "__main__":
    asyncio.run(test_scheduler())
