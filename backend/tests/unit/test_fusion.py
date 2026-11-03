import pytest

from reposcope.retrieval.fusion import reciprocal_rank_fusion


def test_combines_three_rankings():
    hits = reciprocal_rank_fusion([
        [101, 204],
        [204, 101, 305],
        [305, 101, 204],
    ])

    assert [hit.chunk_id for hit in hits] == [101, 204, 305]

    by_id = {hit.chunk_id: hit.score for hit in hits}

    assert by_id[101] == pytest.approx(
        1 / 61 + 1 / 62 + 1 / 62
    )

    assert by_id[204] == pytest.approx(
        1 / 62 + 1 / 61 + 1 / 63
    )

    assert by_id[305] == pytest.approx(
        1 / 63 + 1 / 61
    )


def test_empty_rankings_return_no_hits():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], [], []]) == []


def test_single_list_preserves_rank_order():
    hits = reciprocal_rank_fusion([[30, 10, 20]])

    assert [hit.chunk_id for hit in hits] == [30, 10, 20]
    assert hits[0].score == pytest.approx(1 / 61)
    assert hits[1].score == pytest.approx(1 / 62)
    assert hits[2].score == pytest.approx(1 / 63)


def test_duplicate_ids_do_not_add_votes_or_rank_gaps():
    hits = reciprocal_rank_fusion([[10, 10, 20]])

    assert [hit.chunk_id for hit in hits] == [10, 20]
    assert hits[0].score == pytest.approx(1 / 61)
    assert hits[1].score == pytest.approx(1 / 62)


def test_missing_item_contributes_zero():
    hits = reciprocal_rank_fusion([[10], [], [20]])

    assert [hit.chunk_id for hit in hits] == [10, 20]
    assert all(
        hit.score == pytest.approx(1 / 61)
        for hit in hits
    )


def test_equal_scores_use_ascending_chunk_id():
    hits = reciprocal_rank_fusion([
        [20, 10],
        [10, 20],
    ])

    assert [hit.chunk_id for hit in hits] == [10, 20]
    assert hits[0].score == hits[1].score


def test_limit_is_applied_after_fusion():
    hits = reciprocal_rank_fusion(
        [[10, 20, 30], [30, 20, 10]],
        limit=2,
    )

    assert len(hits) == 2


def test_custom_k():
    hits = reciprocal_rank_fusion([[10]], k=10)

    assert hits[0].score == pytest.approx(1 / 11)


def test_retriever_list_order_does_not_change_results():
    rankings = [
        [10, 20, 30],
        [20, 30, 10],
        [30, 10, 20],
    ]

    assert reciprocal_rank_fusion(rankings) == (
        reciprocal_rank_fusion(list(reversed(rankings)))
    )


@pytest.mark.parametrize("k", [0, -1, True, 1.5, "60"])
def test_rejects_invalid_k(k):
    with pytest.raises(ValueError, match="k must"):
        reciprocal_rank_fusion([[10]], k=k)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "20"])
def test_rejects_invalid_limit(limit):
    with pytest.raises(ValueError, match="limit must"):
        reciprocal_rank_fusion([[10]], limit=limit)


@pytest.mark.parametrize("chunk_id", [0, -1, True, 1.5, "10"])
def test_rejects_invalid_chunk_ids(chunk_id):
    with pytest.raises(ValueError, match="chunk IDs"):
        reciprocal_rank_fusion([[chunk_id]])