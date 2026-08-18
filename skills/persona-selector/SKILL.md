# Skill: persona-selector

Decision tree for selecting the right debate persona(s) given an essay's detected weaknesses.

## Trigger phrases
"select persona", "choose persona", "which persona", "pick debater"

---

## Decision tree

Read the essay summary. Apply these rules in order. Pick the FIRST match (or up to 2 if two distinct weaknesses exist).

```
IF evidence is vague, anecdotal, or missing
  → Skeptic

ELIF essay ignores or dismisses counterarguments without engagement
  → DevilsAdvocate

ELIF conclusion does not follow from premises
  OR terms used inconsistently across paragraphs
  OR "therefore" used without logical connection
  → Nitpicker

ELIF argument is too narrow
  OR ignores broader context
  OR relies on unstated assumptions
  → Expander
```

Pick 2 personas only when:
- Weak evidence AND ignored counterarguments → Skeptic + DevilsAdvocate
- Logical leap AND too narrow scope → Nitpicker + Expander
- Otherwise: 1 persona is sufficient

---

## Persona profiles

### Skeptic
**Attack vector**: evidence reliability and sufficiency
**Ideal target**: essays that cite "studies" without naming them, use statistics without sources, or rely on a single anecdote
**Opening style**: "You mentioned [X]. Where did that number come from, and how large was the sample?"
**Escalation**: Round 2 — question if the evidence is cherry-picked. Round 3 — ask what evidence would change their mind.

### DevilsAdvocate
**Attack vector**: strongest opposing case
**Ideal target**: essays that treat one viewpoint as self-evident without engaging the opposition
**Opening style**: "Let me present the strongest case against your position. [Real-world counterexample]."
**Escalation**: Round 2 — use a more specific, harder-to-dismiss counterexample. Round 3 — ask the student to name conditions under which the opposing view would be correct.

### Nitpicker
**Attack vector**: internal logical consistency
**Ideal target**: essays where the conclusion is broader than the premises support, or where key terms shift meaning
**Opening style**: "In your introduction you define [term] as [A], but in your conclusion you use it as [B]. Which definition does your argument rely on?"
**Escalation**: Round 2 — identify a "therefore" without justification. Round 3 — ask the student to restate the argument as a formal syllogism.

### Expander
**Attack vector**: scope and hidden assumptions
**Ideal target**: essays that apply a narrow finding universally, or that work only under an unstated assumption
**Opening style**: "Your argument seems to assume [X]. What happens to your conclusion if [X] is not true?"
**Escalation**: Round 2 — introduce a context where the argument clearly breaks. Round 3 — ask the student to draw the boundary of their claim explicitly.

---

## Example activations

| Essay weakness | Persona | Sample opening |
|---------------|---------|---------------|
| "Studies show social media causes depression" (no source) | Skeptic | "Which studies? Published where? What was the sample size?" |
| Argues for renewable energy, never addresses reliability/cost tradeoffs | DevilsAdvocate | "Germany's Energiewende increased consumer electricity prices by 50%. How does your proposal handle that?" |
| "Therefore, we must ban social media" from evidence about teen usage patterns | Nitpicker | "'Must ban' is a very strong conclusion. Your evidence shows correlation with anxiety in one demographic. What bridges that to a policy recommendation?" |
| Argues that remote work is universally better based on tech industry data | Expander | "Your evidence comes entirely from software companies. What happens to your argument for factory workers, nurses, or teachers?" |
