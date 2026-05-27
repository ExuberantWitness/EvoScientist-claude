"""Session数据单元: ChunkKind + ChunkRow + ChunkTable"""
from enum import Enum
from dataclasses import dataclass, field


class ChunkKind(str, Enum):
    USER_TEXT = "user_text"
    ASSISTANT_TURN = "assistant_turn"
    SYSTEM_TEXT = "system_text"
    TOOL_FEEDBACK = "tool_feedback"
    PIPELINE_EVENT = "pipeline_event"


@dataclass
class ChunkRow:
    id: str
    kind: ChunkKind
    content: str
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


class ChunkTable:
    def __init__(self):
        self.rows: list[ChunkRow] = []

    def append(self, row: ChunkRow):
        self.rows.append(row)

    def to_messages(self) -> list:
        """转换为LangGraph消费的messages格式"""
        return [{"role": r.kind.value, "content": r.content} for r in self.rows]
