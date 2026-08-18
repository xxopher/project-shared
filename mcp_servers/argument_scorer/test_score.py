import json
from rubric import score_all, score_logical_coherence

sample = "According to WHO, 34% of teens report higher anxiety. While critics argue correlation is not causation, longitudinal studies support the link. Therefore, we must act."
result = score_all(sample)
print(json.dumps(result, indent=2))
print("Logical coherence only:", score_logical_coherence(sample))
