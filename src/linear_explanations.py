"""Signed TF-IDF contributions for a Logistic Regression class contrast."""

import math


def explain_pipeline(pipeline, text, top_k=5):
    vectorizer = pipeline.named_steps["tfidf"]
    classifier = pipeline.named_steps["classifier"]
    vector = vectorizer.transform([text])
    classes = list(classifier.classes_)

    predicted = classifier.predict(vector)[0]
    winner = classes.index(predicted)
    probabilities = classifier.predict_proba(vector)[0]
    alternative = max(
        (index for index in range(len(classes)) if index != winner),
        key=lambda index: float(probabilities[index]),
    )
    decision = classifier.decision_function(vector)

    if len(classes) == 2 and classifier.coef_.shape[0] == 1:
        # Binary coefficients describe class 1 relative to class 0.
        sign = 1 if winner == 1 else -1
        weights = sign * classifier.coef_[0]
        intercept = float(sign * classifier.intercept_[0])
        expected_margin = float(sign * decision[0])
    else:
        weights = classifier.coef_[winner] - classifier.coef_[alternative]
        intercept = float(
            classifier.intercept_[winner] - classifier.intercept_[alternative]
        )
        expected_margin = float(
            decision[0, winner] - decision[0, alternative]
        )

    terms = vectorizer.get_feature_names_out()
    contributions = [
        {
            "term": str(terms[index]),
            "contribution": float(value * weights[index]),
        }
        for index, value in zip(vector.indices, vector.data)
        if value * weights[index] != 0
    ]
    contributions.sort(
        key=lambda item: (-abs(item["contribution"]), item["term"])
    )

    all_terms_total = sum(item["contribution"] for item in contributions)
    reconstructed_margin = intercept + all_terms_total
    if not math.isfinite(reconstructed_margin) or not math.isclose(
        reconstructed_margin, expected_margin, rel_tol=1e-9, abs_tol=1e-9
    ):
        raise ValueError("Explanation does not reconstruct the model margin.")

    strongest = contributions[:top_k]
    for item in strongest:
        item["direction"] = (
            "supports_prediction"
            if item["contribution"] > 0 else "supports_alternative"
        )

    return {
        "predicted_class": str(predicted),
        "alternative_class": str(classes[alternative]),
        "top_terms": strongest,
        "intercept_contribution": intercept,
        "remaining_terms_contribution": (
            all_terms_total - sum(item["contribution"] for item in strongest)
        ),
        "decision_margin": expected_margin,
        "margin_reconstruction_verified": True,
        "note": (
            "Learned text associations, not causal diagnosis. "
            "Contributions are decision-score units, not probabilities."
        ),
    }
