import json
from rubric import score_all

weak = "Social media is obviously bad for everyone. Studies show it causes depression. We should clearly ban it immediately for all teenagers."
strong = "According to Twenge et al. (2018), depression rates in US teens rose 33% between 2010-2015, correlating with smartphone adoption. While critics argue this is correlation not causation, the longitudinal pattern across 15 countries suggests a consistent link. This argument applies specifically to high-income countries with high smartphone penetration."

print("=== Weak argument ===")
print(json.dumps(score_all(weak), indent=2))

print()
print("=== Strong argument ===")
print(json.dumps(score_all(strong), indent=2))
