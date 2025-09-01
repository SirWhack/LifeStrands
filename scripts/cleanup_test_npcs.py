#!/usr/bin/env python3
import os
import asyncio
import argparse
import asyncpg

DEFAULT_DB = "postgresql://lifestrands_user:lifestrands_password@localhost:5432/lifestrands"

TARGET_NAMES = [
    "Test Character",
    "Test NPC",
]

DELETE_SQL = """
DELETE FROM npcs
WHERE name = ANY($1)
   OR (life_strand_data->>'name') = ANY($1)
"""

COUNT_SQL = """
SELECT COUNT(*) FROM npcs
WHERE name = ANY($1)
   OR (life_strand_data->>'name') = ANY($1)
"""

async def main():
    parser = argparse.ArgumentParser(description="Remove test NPCs created by integration tests")
    parser.add_argument("--database-url", dest="db", default=os.getenv("DATABASE_URL", DEFAULT_DB))
    parser.add_argument("--execute", action="store_true", help="Actually perform the deletion")
    args = parser.parse_args()

    pool = await asyncpg.create_pool(args.db)
    async with pool.acquire() as conn:
        to_remove = await conn.fetchval(COUNT_SQL, TARGET_NAMES)
        print(f"Found {to_remove} test NPCs to remove.")
        if to_remove and args.execute:
            res = await conn.execute(DELETE_SQL, TARGET_NAMES)
            print(f"Deleted: {res}")
        elif to_remove:
            print("Dry-run mode. Re-run with --execute to delete.")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())

