import sys, json
sys.path.insert(0, ".")
from rubric import score_all, score_logical_coherence, score_evidence_quality

sample = "According to WHO, 34% of teens report higher anxiety. While critics argue correlation is not causation, longitudinal studies support the link. Therefore, we must act."
print(json.dumps(score_all(sample), indent=2))
print("Logical coherence only:", score_logical_coherence(sample))
