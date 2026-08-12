import asyncio, json
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models import Business, Workspace

async def main():
    async with AsyncSessionLocal() as s:
        businesses = (await s.execute(select(Business))).scalars().all()
        workspaces = (await s.execute(select(Workspace))).scalars().all()
        print(json.dumps({
            'businesses': [{'id': str(b.id), 'business_client_id': b.business_client_id, 'name': b.name} for b in businesses],
            'workspaces': [{'id': str(w.id), 'business_id': str(w.business_id), 'workspace_id': w.workspace_id, 'name': w.name} for w in workspaces],
        }, indent=2))

asyncio.run(main())
