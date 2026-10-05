from pydantic import BaseModel, HttpUrl


class PullRequestAnalysisRequest(BaseModel):
    pull_request_url: HttpUrl