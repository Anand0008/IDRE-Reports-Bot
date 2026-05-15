"""Records latency and token usage. INFORMATIONAL ONLY — no budget enforcement in V10."""
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TokenUsage:
    prompt: int = 0
    completion: int = 0

    @property
    def total(self) -> int:
        return self.prompt + self.completion


@dataclass
class Measurement:
    latency_ms: float = 0.0
    tokens: TokenUsage = field(default_factory=TokenUsage)
    llm_calls: int = 0

    def record_tokens(self, prompt: int = 0, completion: int = 0) -> None:
        self.tokens.prompt += prompt
        self.tokens.completion += completion

    def record_llm_call(self) -> None:
        self.llm_calls += 1

    def to_dict(self) -> dict:
        return {
            "latency_ms": round(self.latency_ms, 1),
            "tokens": {
                "prompt": self.tokens.prompt,
                "completion": self.tokens.completion,
                "total": self.tokens.total,
            },
            "llm_calls": self.llm_calls,
        }


@contextmanager
def measure() -> Iterator[Measurement]:
    m = Measurement()
    start = time.monotonic()
    try:
        yield m
    finally:
        m.latency_ms = (time.monotonic() - start) * 1000
