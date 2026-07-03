"""Knowledge-base API routes."""

from fastapi import APIRouter, Query

from wcpa.data.sources.bing_worldcup import load_bing_manifest, load_bing_records

router = APIRouter()


@router.get("/bing")
async def get_bing_knowledge(limit: int = Query(default=8, ge=1, le=100)):
    """Return Bing Sports knowledge-base manifest and record samples."""
    manifest = load_bing_manifest()
    record_types = ["matches", "bracket", "news", "standings", "player_stats", "teams"]
    return {
        "status": "ready" if manifest else "not_synced",
        "manifest": manifest,
        "samples": {
            record_type: load_bing_records(record_type, limit=limit)
            for record_type in record_types
        },
    }
