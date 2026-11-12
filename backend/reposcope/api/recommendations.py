"""Live recommendation reader. No import-time configuration, DB or network work."""
import asyncio
from typing import Annotated
from fastapi import APIRouter,Depends,HTTPException,Path,Query
from reposcope.contracts.api import RecommendationItem,RecommendationsResponse
from reposcope.recommendations.rationale import RationaleGenerator,deterministic_rationale

from reposcope.integrations.llm_cache import MemoryLLMCache

router=APIRouter(tags=['recommendations'])
_RATIONALE_CACHE=MemoryLLMCache(max_entries=256,ttl_seconds=300)


class DatabaseRecommendationService:
    def read(self,repo_id,snapshot_id,k):
        # Lazy imports preserve /health and API validation without DB configuration.
        from reposcope.db.session import SessionLocal
        from reposcope.recommendations.pipeline import read_recommendations
        with SessionLocal() as session:
            return read_recommendations(session,repo_id,snapshot_id=snapshot_id,k=k)


def get_recommendation_service():
    return DatabaseRecommendationService()


async def get_rationale_generator():
    from reposcope.integrations.llm import LLMClient,LLMConfigurationError
    try:
        client=LLMClient.from_env(max_attempts=1,total_timeout=8,request_timeout=6,cache=_RATIONALE_CACHE)
    except (LLMConfigurationError,ValueError):
        yield RationaleGenerator()
        return
    async with client:
        yield RationaleGenerator(client)


@router.get('/repos/{repo_id}/recommendations',response_model=RecommendationsResponse)
async def get_recommendations(
    repo_id:Annotated[int,Path(gt=0)],
    k:Annotated[int,Query(ge=1,le=100)]=10,
    snapshot_id:Annotated[int|None,Query(gt=0)]=None,
    service=Depends(get_recommendation_service),
    generator=Depends(get_rationale_generator),
):
    from starlette.concurrency import run_in_threadpool
    from reposcope.recommendations.pipeline import RecommendationNotFound,RecommendationsNotReady
    try:
        published=await run_in_threadpool(service.read,repo_id,snapshot_id,k)
    except RecommendationNotFound as exc:
        raise HTTPException(status_code=404,detail=str(exc)) from None
    except RecommendationsNotReady as exc:
        raise HTTPException(status_code=409,detail=str(exc)) from None
    # At most ten LLM calls, bounded concurrently; remaining items use exact fallback.
    sem=asyncio.Semaphore(3)
    async def explain(index,item):
        if index>=10:return deterministic_rationale(item['facts'],'LLM_BATCH_LIMIT')
        async with sem:return await generator.generate(item['facts'])
    explanations=await asyncio.gather(*(explain(i,row) for i,row in enumerate(published.items)))
    items=[]
    for row,explanation in zip(published.items,explanations):
        values=dict(row['finding']);values['id']=row['id']
        items.append(RecommendationItem(**values,rationale=explanation.text,
            rationale_source=explanation.source,
            rationale_degraded_reason=explanation.degraded_reason,
            feature_citations=[c.model_dump() for c in explanation.citations],
            computed_features={**row['features'],'applied_effort':row['facts'].values['effort'],
                'category_multiplier':row['facts'].values['category_multiplier']},
            detector_evidence=row['evidence']))
    return RecommendationsResponse(recommendations=items,repo_id=published.repo_id,
        snapshot_id=published.snapshot_id,commit_sha=published.commit_sha,run_id=published.run_id,
        gaps=list(published.gaps))
