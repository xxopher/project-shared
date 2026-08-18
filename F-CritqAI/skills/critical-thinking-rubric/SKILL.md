# Skill: critical-thinking-rubric

Teaches agents how to evaluate argument quality using the Paul-Elder critical thinking framework.

## Trigger phrases
"evaluate argument", "score thinking", "assess reasoning", "phản biện", "đánh giá lập luận"

---

## Paul-Elder Framework — 4 Dimensions

### 1. Logical Coherence (0–5)
**What it measures**: Do claims follow from premises? Are connectives used properly?

| Score | Description |
|-------|-------------|
| 5 | Multiple "therefore/because/thus" with no non-sequiturs |
| 4 | Clear logical flow, one minor leap |
| 3 | Some connectives but at least one unjustified step |
| 2 | Minimal logical connectors, some "obviously/clearly" shortcuts |
| 1 | Conclusion does not follow from stated evidence |
| 0 | No logical structure; claims appear disconnected |

**Strong example**: "Because the sample included only urban schools (premise), we cannot conclude this applies nationally (limit on conclusion)."
**Weak example**: "Obviously, social media causes depression. Therefore we should ban it."

---

### 2. Evidence Quality (0–5)
**What it measures**: Is evidence concrete, specific, and cited? Or vague and asserted?

| Score | Description |
|-------|-------------|
| 5 | 3+ specific citations/data points with source |
| 4 | 2 specific data points |
| 3 | 1 specific citation, no vague assertions |
| 2 | 1 specific citation + vague assertions mixed |
| 1 | Only vague assertions ("studies show", "it's clear") |
| 0 | No evidence at all |

**Strong example**: "According to WHO (2023), screen time over 4 hours/day correlates with depression in 34% of adolescents surveyed across 15 countries."
**Weak example**: "Many studies show social media is harmful."

---

### 3. Counterargument Handling (0–5)
**What it measures**: Does the student acknowledge opposing views and respond to them?

| Score | Description |
|-------|-------------|
| 5 | 3+ acknowledgments with substantive engagement |
| 4 | 2 acknowledgments, addressed thoughtfully |
| 3 | 1 acknowledgment with genuine engagement |
| 2 | 1 acknowledgment but dismissed without reasoning |
| 1 | Counterarguments ignored entirely |
| 0 | Student attacks opposing view rather than engaging it |

**Strong example**: "While proponents of social media argue it connects isolated communities — and this is a genuine benefit — the harm to adolescent mental health documented in clinical settings may outweigh this social benefit."
**Weak example**: "Some people think social media is fine, but they are wrong."

---

### 4. Scope Awareness (0–5)
**What it measures**: Does the student recognize the limits of their argument?

| Score | Description |
|-------|-------------|
| 5 | Explicitly hedges claims, states scope, notes edge cases |
| 4 | Hedges most claims, acknowledges one limitation |
| 3 | Some hedging language, occasional overgeneralization |
| 2 | Mostly overgeneralizes; one hedged claim |
| 1 | Sweeping generalizations throughout ("always", "everyone") |
| 0 | Claims universal truth from single anecdote |

**Strong example**: "This argument applies specifically to adolescents (ages 13-17) in high-income countries, and may not generalize to other age groups or contexts."
**Weak example**: "Social media is always harmful for everyone."

---

## Round escalation templates

### Round 1 — Probe (open the question)
- "You cited [X]. How was that data collected?"
- "Your claim is that [X]. What would it take for that to be false?"
- "You use the word [term] — what exactly do you mean by it?"

### Round 2 — Push harder (expose the gap)
- "You said [X] is evidence for [Y]. But couldn't [X] also be explained by [Z]?"
- "A strong objection would be [counterexample]. How does your argument handle that?"
- "In your last response you said [A] and also [B]. Are those consistent?"

### Round 3 — Corner (force precision or admission)
- "If [your core assumption] turned out to be wrong, does your entire argument collapse?"
- "You've addressed [X] but not [Y]. Is [Y] outside the scope of your argument, or did you not consider it?"
- "Give me one real-world case where your conclusion holds AND one where it doesn't."

---

## What counts as a good student response (for Analytics Agent)

A response that IMPROVES the session score will:
- Add a specific citation or data point not mentioned before
- Acknowledge a limit on the argument ("this applies only to...")
- Directly engage the persona's challenge rather than restating the original claim
- Use "therefore/because/however" to connect new reasoning

A response that DOES NOT improve the score will:
- Repeat the original claim in different words
- Assert "but I still think X" without new reasoning
- Attack the persona rather than the argument
