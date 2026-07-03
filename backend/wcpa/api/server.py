"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from wcpa.api.routes import agents, bracket, data, groups, health, knowledge, matches, predict, predictions, teams, worldcup
from wcpa.worldcup.scheduler import scheduler

app = FastAPI(
    title="World Cup Oracle",
    description="World Cup prediction command center with Bing Sports knowledge base.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["predictions"])
app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(bracket.router, prefix="/api/bracket", tags=["bracket"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(predict.router, prefix="/api/predict", tags=["predict"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(worldcup.router, prefix="/api/worldcup", tags=["worldcup"])


@app.on_event("startup")
async def start_worldcup_scheduler():
    scheduler.start()


@app.on_event("shutdown")
async def stop_worldcup_scheduler():
    await scheduler.stop()
