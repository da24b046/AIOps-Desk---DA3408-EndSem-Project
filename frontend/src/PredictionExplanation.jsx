export default function PredictionExplanation({ explanation }) {
  return (
    <details className="feedback-panel">
      <summary>Why did the model suggest this?</summary>
      {explanation?.status !== 'available' ? (
        <p>Explanations are unavailable for this saved prediction.</p>
      ) : (
        <>
          <p>
            These are learned text associations, not a diagnosis.
            Contributions are model decision-score units, not probabilities.
          </p>
          {['category', 'priority'].map((target) => {
            const detail = explanation[target]
            return (
              <section key={target}>
                <h3>{target === 'category' ? 'Category' : 'Priority'} explanation</h3>
                <p>
                  Comparing <strong>{detail.predicted_class}</strong> with
                  {' '}<strong>{detail.alternative_class}</strong>.
                </p>
                {detail.top_terms.length === 0 ? (
                  <p>No vocabulary terms matched. The model bias determined this comparison.</p>
                ) : (
                  <ul>
                    {detail.top_terms.map((item) => (
                      <li key={item.term}>
                        <strong>{item.term}</strong>
                        {' — '}supports {item.direction === 'supports_prediction'
                          ? detail.predicted_class : detail.alternative_class}
                        {' '}({item.contribution > 0 ? '+' : ''}
                        {item.contribution.toFixed(3)})
                      </li>
                    ))}
                  </ul>
                )}
                <p className="muted">
                  Other terms and the model bias also contribute to the result.
                </p>
              </section>
            )
          })}
        </>
      )}
    </details>
  )
}
