import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient

from reposcope.main import app
from reposcope.api.recommendations import (
    get_recommendation_service,
    get_rationale_generator,
)
from reposcope.recommendations.rationale import RationaleGenerator
from reposcope.recommendations.pipeline import read_recommendations
from test_recommendation_pipeline import db, publish


@pytest.fixture
def client(db):
    class Service:
        def read(self, repo_id, snapshot_id, k):
            return read_recommendations(
                db,
                repo_id,
                snapshot_id=snapshot_id,
                k=k,
            )

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_recommendation_service] = lambda: Service()
    app.dependency_overrides[get_rationale_generator] = (
        lambda: RationaleGenerator()
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_live_persisted_response_and_contract(db, client):
    from reposcope.contracts.api import RecommendationsResponse

    publish(db)
    response = client.get("/api/repos/1/recommendations")

    assert response.status_code == 200, response.text

    body = RecommendationsResponse.model_validate(response.json())
    assert body.repo_id == 1
    assert body.snapshot_id == 1
    assert len(body.recommendations) == 3

    for item in body.recommendations:
        assert item.rationale_source == "deterministic"
        assert item.feature_citations
        assert item.rationale
        assert item.computed_features


def test_route_registered_exactly_once():
    import fastapi.routing as routing
    from reposcope.api.recommendations import get_recommendations

    iterator = getattr(routing, "iter_route_contexts", None)

    if iterator is not None:
        effective_routes = list(iterator(app.routes))
    else:
        effective_routes = []

        for route in app.routes:
            expand = getattr(route, "effective_route_contexts", None)

            if callable(expand):
                effective_routes.extend(expand())
            else:
                effective_routes.append(route)

    matches = [
        route
        for route in effective_routes
        if getattr(route, "path", None)
        == "/api/repos/{repo_id}/recommendations"
        and "GET" in (getattr(route, "methods", None) or ())
    ]

    assert len(matches) == 1
    assert matches[0].endpoint is get_recommendations


@pytest.mark.parametrize(
    "query",
    [
        "?k=0",
        "?k=101",
        "?snapshot_id=0",
        "?k=nope",
    ],
)
def test_query_validation_without_database(query):
    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/repos/1/recommendations" + query
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_repo_is_404(client):
    response = client.get("/api/repos/999/recommendations")

    assert response.status_code == 404


def test_unpublished_is_409_not_mock_data(client):
    response = client.get("/api/repos/1/recommendations")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_valid_empty_snapshot_response(db, client):
    from reposcope.models.repository_snapshot import RepositorySnapshot
    from reposcope.recommendations.pipeline import (
        publish_recommendations,
    )
    from reposcope.recommendations.detectors import CandidateDataset

    db.add(
        RepositorySnapshot(
            id=2,
            repository_id=1,
            commit_sha="b" * 40,
            status="ready",
            error_message=None,
            indexed_at=None,
        )
    )
    db.commit()

    publish_recommendations(
        db,
        CandidateDataset(repo_id=1, snapshot_id=2),
    )
    db.commit()

    response = client.get("/api/repos/1/recommendations")

    assert response.status_code == 200
    assert response.json()["recommendations"] == []


def test_limit_and_scope(db, client):
    publish(db)

    limited = client.get("/api/repos/1/recommendations?k=1")

    assert limited.status_code == 200
    assert len(limited.json()["recommendations"]) == 1

    foreign_snapshot = client.get(
        "/api/repos/2/recommendations?snapshot_id=1"
    )

    assert foreign_snapshot.status_code == 404