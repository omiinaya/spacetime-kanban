"""Agent endpoints for spacetimedb-kanban."""

import time

from fastapi import APIRouter, Depends, HTTPException

from shared import (
    _call,
    _sanitize,
    _sql,
    _sql_param,
    verify_auth,
)
from shared import (
    AgentCapabilitiesRequest,
    AgentHeartbeatRequest,
    AgentOut,
    AgentRegisterRequest,
)

router = APIRouter()


async def _row_to_agent(r: dict) -> AgentOut:
    return AgentOut(
        id=r["id"],
        host=r.get("host", ""),
        capabilities=r.get("capabilities"),
        repo_focus=r.get("repo_focus"),
        current_task_id=r.get("current_task_id"),
        status=r.get("status", "offline"),
        last_heartbeat=r.get("last_heartbeat", 0),
        first_seen=r.get("first_seen", 0),
    )


@router.post("/api/agents/register", dependencies=[Depends(verify_auth)])
async def register_agent(body: AgentRegisterRequest):
    """Register or re-connect an agent in the swarm."""
    await _call("register_agent", [body.agent_id, body.host, body.capabilities, body.repo_focus])
    return {"status": "registered", "agent_id": body.agent_id}


@router.post("/api/agents/{agent_id}/heartbeat", dependencies=[Depends(verify_auth)])
async def agent_heartbeat(agent_id: str, body: AgentHeartbeatRequest):
    """Send a heartbeat to the swarm."""
    await _call("agent_heartbeat", [agent_id, body.status, body.current_task_id])
    return {"status": "ok", "agent_id": agent_id}


@router.put("/api/agents/{agent_id}/capabilities")
async def set_agent_capabilities(agent_id: str, body: AgentCapabilitiesRequest):
    """Update an agent's capabilities and repo focus."""
    await _call("set_agent_capabilities", [agent_id, body.capabilities, body.repo_focus])
    return {"status": "updated", "agent_id": agent_id}


@router.get("/api/agents/health")
async def agent_health():
    """Return all agents enriched with current task details and staleness."""
    agents = await _sql("SELECT * FROM swarm_agents")
    tasks = await _sql("SELECT id, title, description, status, priority, repo FROM tasks")
    task_map = {t["id"]: t for t in tasks}

    now_ms = int(time.time() * 1000)
    stale_threshold = 5 * 60 * 1000  # 5 minutes

    result = []
    for r in agents:
        aid = r.get("id", "")
        current_task_id = r.get("current_task_id")
        task_info = None
        if current_task_id and current_task_id in task_map:
            t = task_map[current_task_id]
            task_info = {
                "id": t["id"],
                "title": t["title"],
                "status": t.get("status", ""),
                "priority": t.get("priority", 2),
                "repo": t.get("repo", ""),
            }

        last_hb = r.get("last_heartbeat", 0)
        age_ms = now_ms - last_hb
        stale = age_ms > stale_threshold if last_hb > 0 else True

        result.append({
            "id": aid,
            "host": r.get("host", ""),
            "status": r.get("status", "offline"),
            "capabilities": r.get("capabilities"),
            "repo_focus": r.get("repo_focus"),
            "current_task": task_info,
            "last_heartbeat": last_hb,
            "heartbeat_age_seconds": max(0, age_ms // 1000) if last_hb > 0 else -1,
            "stale": stale,
            "first_seen": r.get("first_seen", 0),
        })

    result.sort(key=lambda a: -a["last_heartbeat"])
    return result


@router.get("/api/agents", response_model=list[AgentOut])
async def list_agents():
    """List all registered swarm agents."""
    rows = await _sql("SELECT * FROM swarm_agents")
    agents = []
    for r in rows:
        a = await _row_to_agent(r)
        agents.append(a)
    agents.sort(key=lambda a: -a.last_heartbeat)
    return agents


@router.get("/api/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str):
    """Get a specific swarm agent's details."""
    rows = await _sql_param("SELECT * FROM swarm_agents WHERE id = '{agent_id}'", agent_id=agent_id)
    if not rows:
        raise HTTPException(404, "Agent not found")
    return await _row_to_agent(rows[0])
