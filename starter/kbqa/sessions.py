"""对话历史。

按 `session_id` 分开存：契约 §5 要求「同一个 session_id 的多次请求视为同一段对话」，
同时「不同 session_id 之间不能串线」。

原来的实现是一条**平铺列表**——`history()` 不管传什么 session_id 都返回同一条，
`append()` 也不看 session_id。后果不只是串线：`max_turns` 那个「最近几轮」的窗口
也变成了全局的，一个人的追问会把另一个人的上文挤掉。`max_sessions` 更是完全没用上。
"""

from __future__ import annotations

import threading
from typing import Optional

MAX_TURNS = 6
MAX_SESSIONS = 500


class SessionStore:
    """每个会话各自保留最近几轮，够解追问就行。"""

    def __init__(self, max_sessions: int = MAX_SESSIONS, max_turns: int = MAX_TURNS) -> None:
        self._sessions: dict[str, list[dict]] = {}
        #: 最近使用顺序，队首最旧。用来在会话数超限时淘汰。
        self._recent: list[str] = []
        self._lock = threading.Lock()
        self.max_sessions = max_sessions
        self.max_turns = max_turns

    @staticmethod
    def _key(session_id: Optional[str]) -> str:
        return (session_id or "").strip()

    def history(self, session_id: Optional[str]) -> list[dict]:
        """没带 `session_id` 就没有「同一段对话」可言，返回空历史。"""
        key = self._key(session_id)
        if not key:
            return []
        with self._lock:
            return list(self._sessions.get(key, ()))

    def append(self, session_id: Optional[str], turn: dict) -> None:
        key = self._key(session_id)
        if not key:
            return
        with self._lock:
            turns = self._sessions.setdefault(key, [])
            turns.append(turn)
            del turns[: max(0, len(turns) - self.max_turns)]
            if key in self._recent:
                self._recent.remove(key)
            self._recent.append(key)
            while len(self._recent) > self.max_sessions:
                self._sessions.pop(self._recent.pop(0), None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._recent.clear()
