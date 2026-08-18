# Skill: answer-leak-patterns

Teaches the Challenge Validator Agent how to identify instances where the AI inadvertently provides an answer or does the reasoning work for the student.

## Trigger phrases
"check for answer leaks", "validate challenge", "check if answer is given", "kiểm tra rò rỉ đáp án"

---

## The Rule of Pedagogical Withholding

The core principle of CritiqAI is that **the AI must only ask questions or point out logical gaps; it must never supply the missing information, correct the premise directly, or propose a better argument.**

If the AI does the reasoning for the student, the pedagogical value of the system is destroyed.

---

## 18 Deterministic Answer-Leak Patterns

The Validator Agent checks generated challenges against specific patterns. If any of these patterns (or their semantic equivalents) are found, the challenge MUST be rejected.

### Category 1: Direct Correction (The "Actually" Pattern)
The AI directly tells the student they are wrong and provides the right fact.

- **English Patterns**: "Actually, ...", "The correct answer is...", "In fact, ...", "The reality is...", "Studies show that [specific fact]..."
- **Vietnamese Patterns**: "Thực ra...", "Câu trả lời đúng là...", "Sự thật là...", "Trên thực tế..."
- **Example of Leak**: "Actually, the First Amendment does not protect speech that incites violence." (Reject)
- **Safe Alternative**: "You claimed the First Amendment protects all speech. Are there any historical Supreme Court exceptions to this rule?"

### Category 2: Supplying Missing Evidence (The "You should mention" Pattern)
The AI hands the student a piece of evidence they failed to find themselves.

- **English Patterns**: "You should mention...", "A good example is...", "Consider adding the fact that...", "For instance, [fact]..."
- **Vietnamese Patterns**: "Bạn nên nhắc đến...", "Một ví dụ tốt là...", "Lẽ ra bạn nên...", "Bạn có thể dùng ví dụ..."
- **Example of Leak**: "You should mention the Stanford Prison Experiment to back up your point." (Reject)
- **Safe Alternative**: "You made a strong claim about human conformity. What specific psychological studies support this?"

### Category 3: Restructuring the Argument (The "A better way" Pattern)
The AI rewrites or improves the student's phrasing or argumentative structure.

- **English Patterns**: "A better way to phrase this is...", "Instead of saying X, say Y...", "Your argument would be stronger if you said..."
- **Vietnamese Patterns**: "Một cách diễn đạt tốt hơn là...", "Thay vì nói X, hãy nói Y...", "Lập luận của bạn sẽ chặt chẽ hơn nếu..."
- **Example of Leak**: "A better way to phrase this is 'correlation does not imply causation'." (Reject)
- **Safe Alternative**: "You noticed two things happening at the same time. Does one necessarily cause the other?"

### Category 4: The Rhetorical Give-Away
The AI asks a question but embeds the exact answer within the question itself.

- **English Patterns**: "Don't you think that [correct answer]?", "Isn't it true that [missing fact]?"
- **Vietnamese Patterns**: "Chẳng phải là [đáp án] sao?", "Có đúng là [sự thật] không?"
- **Example of Leak**: "Isn't it true that renewable energy is currently more expensive to store than fossil fuels?" (Reject)
- **Safe Alternative**: "You stated renewable energy is ready to completely replace fossil fuels today. What are the current logistical limitations of battery storage?"

---

## Validation Logic Flow

When evaluating a challenge:
1. **Regex Fast-Path**: Run the challenge against the 18 deterministic patterns (in the system code). If matched -> FAIL.
2. **Semantic Check**: If no regex match, use LLM logic to ask: "Does this challenge contain factual information the student did not provide?" -> If yes -> FAIL.
3. **Action Rule**: If a challenge asks the student to think, it PASSES. If it gives the student something to copy-paste, it FAILS.

## Escalation
If a leak is detected, the Validator Agent will instruct the Debate Agent: "REJECTED: Answer leak detected. You provided the missing fact. Regenerate the challenge by asking a question that forces the student to find that fact themselves."
