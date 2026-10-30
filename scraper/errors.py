from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    rule_id: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule_id}] {self.message}"


class ScrapeError(Exception):
    def __init__(self, rule_id: str, message: str):
        super().__init__(f"[{rule_id}] {message}")
        self.rule_id = rule_id
        self.message = message


class ValidationError(Exception):
    def __init__(self, violations: list[Violation]):
        super().__init__("; ".join(str(v) for v in violations))
        self.violations = violations
