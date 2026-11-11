"""Known coefficient fixtures verify signed contributions and class contrasts."""

import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.linear_explanations import explain_pipeline


def make_pipeline(labels):
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            vocabulary={"alpha": 0, "beta": 1},
            norm=None,
            use_idf=False,
        )),
        ("classifier", LogisticRegression()),
    ])
    texts = (
        ["alpha", "alpha alpha", "beta", "beta beta"]
        if len(labels) == 4 else ["alpha", "beta", "alpha beta"]
    )
    pipeline.fit(texts, labels)
    return pipeline


def binary_pipeline():
    pipeline = make_pipeline(["Medium", "Medium", "High", "High"])
    classifier = pipeline.named_steps["classifier"]
    assert list(classifier.classes_) == ["High", "Medium"]
    classifier.coef_ = np.array([[2.0, -1.0]])
    classifier.intercept_ = np.array([0.25])
    return pipeline


@pytest.mark.parametrize("text,predicted,margin", [
    ("alpha", "Medium", 2.25),
    ("beta", "High", 0.75),
    ("alpha beta", "Medium", 1.25),
])
def test_binary_contributions_have_correct_sign_and_margin(text, predicted, margin):
    result = explain_pipeline(binary_pipeline(), text)
    assert result["predicted_class"] == predicted
    assert result["decision_margin"] == pytest.approx(margin)
    reconstructed = (
        result["intercept_contribution"]
        + sum(item["contribution"] for item in result["top_terms"])
        + result["remaining_terms_contribution"]
    )
    assert reconstructed == pytest.approx(margin)
    if text == "alpha beta":
        terms = {item["term"]: item for item in result["top_terms"]}
        assert terms["alpha"]["contribution"] == pytest.approx(2.0)
        assert terms["beta"]["contribution"] == pytest.approx(-1.0)
        assert terms["beta"]["direction"] == "supports_alternative"


def test_unfamiliar_text_reports_intercept_only():
    result = explain_pipeline(binary_pipeline(), "unseen vocabulary")
    assert result["top_terms"] == []
    assert result["predicted_class"] == "Medium"
    assert result["decision_margin"] == pytest.approx(0.25)
    assert result["intercept_contribution"] == pytest.approx(0.25)


def test_multiclass_contrast_and_omitted_terms():
    pipeline = make_pipeline(["A", "B", "C"])
    classifier = pipeline.named_steps["classifier"]
    classifier.coef_ = np.array([
        [2.0, 0.0],
        [0.0, 2.0],
        [-1.0, -1.0],
    ])
    classifier.intercept_ = np.array([0.0, 0.2, 0.0])

    result = explain_pipeline(pipeline, "alpha beta", top_k=1)
    assert result["predicted_class"] == "B"
    assert result["alternative_class"] == "A"
    assert result["decision_margin"] == pytest.approx(0.2)
    assert len(result["top_terms"]) == 1
    assert result["top_terms"][0]["term"] == "alpha"
    assert result["top_terms"][0]["contribution"] == pytest.approx(-2.0)
    assert result["remaining_terms_contribution"] == pytest.approx(2.0)
