import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class LLMClient:
    # Approximate blended rate for llama-3.3-70b-versatile
    # ($0.59 per 1M input tokens / $0.79 per 1M output tokens)
    # Simplified to a blended average since we track total tokens,
    # not input/output split separately.
    COST_PER_1K_TOKENS = 0.0007

    def __init__(self):
        self.client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    def synthesize(self, texts: list[str]) -> dict:
        """
        Synthesizes a list of source texts into a summary.
        Returns {'text': ..., 'tokens': ...}
        """
        combined = "\n\n---\n\n".join(texts)
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Synthesize the following sources into a concise, well-organized summary (3-5 sentences)."},
                {"role": "user", "content": combined}
            ]
        )
        return {
            "text": response.choices[0].message.content,
            "tokens": response.usage.total_tokens,
        }

    def estimate_cost(self, tokens: int) -> float:
        """Returns an approximate USD cost for a given token count."""
        return round((tokens / 1000) * self.COST_PER_1K_TOKENS, 6)

    def fallback_summary(self, texts: list[str]) -> dict:
        """
        Degraded, non-LLM fallback used when synthesis is unavailable
        (circuit open, retries exhausted). Returns the first fetched
        snippet, truncated, rather than nothing at all.
        """
        if not texts:
            return {"text": "No summary available — no content could be retrieved.", "tokens": 0}
        snippet = texts[0][:400].rsplit(".", 1)[0] + "."
        return {"text": f"[Fallback — LLM summary unavailable] {snippet}", "tokens": 0}


if __name__ == "__main__":
    client = LLMClient()
    fake_sources = [
        "Multi-agent systems consist of multiple interacting intelligent agents.",
        "The circuit breaker pattern prevents cascading failures in distributed systems."
    ]
    result = client.synthesize(fake_sources)
    cost = client.estimate_cost(result["tokens"])
    print("SUMMARY:", result["text"])
    print("TOKENS USED:", result["tokens"])
    print("ESTIMATED COST: $", cost)