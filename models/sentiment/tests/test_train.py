from sentiment_service.train import VARIANTS, build_pipeline, make_broken


def label_sorted_dataset(n: int = 1000) -> tuple[list[str], list[int]]:
    """Mimics the real train split: all positives first, then all negatives."""
    texts = [f"review {i}" for i in range(n)]
    labels = [1] * (n // 2) + [0] * (n - n // 2)
    return texts, labels


def test_make_broken_keeps_both_classes() -> None:
    texts, labels = label_sorted_dataset()
    broken_texts, broken_labels = make_broken(texts, labels, seed=13)

    assert len(broken_texts) == len(broken_labels) == 200
    assert set(broken_labels) == {0, 1}


def test_make_broken_shuffles_labels() -> None:
    texts, labels = label_sorted_dataset()
    original = dict(zip(texts, labels, strict=True))
    broken_texts, broken_labels = make_broken(texts, labels, seed=13)

    mismatches = sum(original[t] != y for t, y in zip(broken_texts, broken_labels, strict=True))
    assert mismatches > 50  # roughly half the labels should now be wrong


def test_make_broken_is_deterministic() -> None:
    texts, labels = label_sorted_dataset()
    assert make_broken(texts, labels, seed=13) == make_broken(texts, labels, seed=13)


def test_build_pipeline_fits_and_predicts() -> None:
    pipeline = build_pipeline(seed=0, min_df=1)
    pipeline.fit(["good great fine", "bad awful poor"], [1, 0])
    proba = pipeline.predict_proba(["great"])
    assert proba.shape == (1, 2)


def test_variant_configs() -> None:
    assert set(VARIANTS) == {"v1", "v2", "v3"}
    assert VARIANTS["v2"].broken
    assert not VARIANTS["v1"].broken and not VARIANTS["v3"].broken
    assert "validation" in VARIANTS["v3"].splits
    assert VARIANTS["v1"].seed != VARIANTS["v3"].seed
