/**
 * The answer's words, with its numbers picked out. The numbers are the part a
 * reader scans for ("12,400", "38%"), so each gets a quiet highlight -- and
 * dir="ltr", so "1,234.5" and "-3%" keep their shape inside an Arabic sentence.
 * Text only: no markup from the model is ever interpreted.
 */
const NUM = /([-+]?\d[\d,]*(?:\.\d+)?%?)/g

export default function AnswerText({ text }: { text: string }) {
  const parts = text.split(NUM)
  return (
    <p className="dl-answer-text" data-testid="answer-text" dir="auto">
      {parts.map((p, i) => (i % 2 === 1
        ? <mark key={i} className="dl-num" dir="ltr">{p}</mark>
        : p))}
    </p>
  )
}
