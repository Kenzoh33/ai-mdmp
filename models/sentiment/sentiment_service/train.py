"""Train the demo sentiment model variants on the Rotten Tomatoes movie reviews dataset.

v1: healthy model on the full train split.
v2: deliberately broken model (small random slice with shuffled labels).
v3: healthy retrain on train + validation with a different seed.

Usage: python -m sentiment_service.train --variant v1 --out /app/model
"""

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

DATASET = "cornell-movie-review-data/rotten_tomatoes"
LABELS = ("negative", "positive")  # dataset label 0 -> negative, 1 -> positive
V2_SAMPLE_SIZE = 200


@dataclass(frozen=True)
class VariantConfig:
    seed: int
    splits: tuple[str, ...]
    broken: bool = False


VARIANTS: dict[str, VariantConfig] = {
    "v1": VariantConfig(seed=42, splits=("train",)),
    "v2": VariantConfig(seed=13, splits=("train",), broken=True),
    "v3": VariantConfig(seed=7, splits=("train", "validation")),
}


def build_pipeline(seed: int, min_df: int = 2) -> Pipeline:
    """TF-IDF over word unigrams and bigrams, followed by logistic regression."""
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=min_df, sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=1000, random_state=seed)),
        ]
    )


def load_rotten_tomatoes(splits: tuple[str, ...]) -> tuple[list[str], list[int]]:
    """Download the given splits. `datasets` is imported here so only training needs it."""
    from datasets import load_dataset

    texts: list[str] = []
    labels: list[int] = []
    for split in splits:
        ds = load_dataset(DATASET, split=split)
        texts.extend(ds["text"])
        labels.extend(ds["label"])
    return texts, labels


def make_broken(
    texts: list[str], labels: list[int], seed: int, size: int = V2_SAMPLE_SIZE
) -> tuple[list[str], list[int]]:
    """Random slice with shuffled labels. Sampling at random (not the first rows) keeps both
    classes present, which logistic regression needs in order to fit."""
    rng = random.Random(seed)
    idx = rng.sample(range(len(texts)), size)
    sampled_texts = [texts[i] for i in idx]
    sampled_labels = [labels[i] for i in idx]
    rng.shuffle(sampled_labels)
    return sampled_texts, sampled_labels


def train_variant(variant: str, out_dir: Path) -> dict[str, object]:
    config = VARIANTS[variant]
    texts, labels = load_rotten_tomatoes(config.splits)
    if config.broken:
        texts, labels = make_broken(texts, labels, config.seed)

    pipeline = build_pipeline(config.seed)
    pipeline.fit(texts, labels)

    test_texts, test_labels = load_rotten_tomatoes(("test",))
    accuracy = float(pipeline.score(test_texts, test_labels))

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out_dir / "model.joblib")
    meta: dict[str, object] = {
        "variant": variant,
        "seed": config.seed,
        "splits": list(config.splits),
        "broken": config.broken,
        "n_train": len(texts),
        "test_accuracy": round(accuracy, 4),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train a sentiment model variant.")
    parser.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--out", type=Path, required=True, help="directory for model.joblib")
    args = parser.parse_args(argv)
    print(json.dumps(train_variant(args.variant, args.out)))


if __name__ == "__main__":
    main()
