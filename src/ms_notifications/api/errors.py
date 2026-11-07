from dataclasses import dataclass, field


@dataclass(slots=True)
class APIProblem(Exception):
    status_code: int
    code: str
    message: str
    headers: dict[str, str] = field(default_factory=dict)
