import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from agent.loop import run_agent
from agent.models import AgentResponse
from agent.pdf import generate_pdf

app = FastAPI(title="GA4 AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    timeout: int = 120


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=AgentResponse)
async def query(request: QueryRequest):
    try:
        return await asyncio.wait_for(run_agent(request.question), timeout=request.timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/pdf")
async def query_pdf(request: QueryRequest):
    try:
        result = await asyncio.wait_for(run_agent(request.question), timeout=request.timeout)
        return Response(content=generate_pdf(result, request.question), media_type="application/pdf")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
