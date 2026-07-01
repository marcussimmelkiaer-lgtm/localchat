from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Callable


class ChatSession:
    def __init__(self, chat):
        self.chat = chat
        self.lock = threading.Lock()


class SessionRegistry:
    """LRU cache of one NobodyWho `Chat` per conversation. The Chats share a
    single reference-counted `Model` (weights loaded once); each only holds its
    own context. Eviction drops the Python object — conversation history lives in
    SQLite and is re-applied per turn, so eviction is lossless."""

    def __init__(self, build_chat: Callable[[], object], max_live: int):
        self._build = build_chat
        self._max = max(1, max_live)
        self._chats: "OrderedDict[str, ChatSession]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, conv_id: str) -> ChatSession:
        with self._lock:
            s = self._chats.get(conv_id)
            if s is not None:
                self._chats.move_to_end(conv_id)
                return s
        # Build outside the registry lock (may load context); then re-check.
        chat = self._build()
        with self._lock:
            existing = self._chats.get(conv_id)
            if existing is not None:
                return existing
            s = ChatSession(chat)
            self._chats[conv_id] = s
            self._chats.move_to_end(conv_id)
            self._evict_locked()
            return s

    def _evict_locked(self):
        while len(self._chats) > self._max:
            evicted = False
            for cid in list(self._chats.keys()):
                if cid == next(reversed(self._chats)):
                    continue  # never evict the most-recently-used
                sess = self._chats[cid]
                if sess.lock.acquire(blocking=False):
                    sess.lock.release()
                    del self._chats[cid]
                    evicted = True
                    break
            if not evicted:
                break

    def evict(self, conv_id: str):
        with self._lock:
            self._chats.pop(conv_id, None)

    def clear(self):
        """Drop every cached Chat (used when the underlying Model is swapped).

        Safe to call mid-generation: a running stream holds its Chat in a local
        variable, so dropping the registry entry never interrupts it. New turns
        rebuild their Chat against whatever Model the engine now holds."""
        with self._lock:
            self._chats.clear()
