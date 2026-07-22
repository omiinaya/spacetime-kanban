"""Scanner API endpoint — trigger repo scans on demand."""
import asyncio
import functools

from fastapi import APIRouter

router = APIRouter(tags=["scanner"])


@router.post("/api/scanner/scan")
async def trigger_scan():
    """Run all repo scanners and create tasks for findings.

    Runs in a thread to avoid blocking the event loop.
    Returns summary of findings and created tasks.
    """
    from scanners.runner import run_all_scanners

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, functools.partial(run_all_scanners))
    total_findings = sum(c.get("finding_count", 0) for c in results.values())
    total_created = sum(c.get("created", 0) for c in results.values())

    return {
        "status": "ok",
        "total_findings": total_findings,
        "total_created": total_created,
        "details": results,
    }
