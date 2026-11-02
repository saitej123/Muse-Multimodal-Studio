"""Layered Memory Architecture for the Agentic AI Harness.

Provides three memory tiers following 2026 agent harness engineering standards:
  1. Working Memory: Ephemeral scratchpad, active plan checklist, and turn context.
  2. Checkpoint Memory: Episodic execution trace with run receipts and JSONL audit logging.
  3. Long-Term Semantic Memory: namespaced, keyword/tag recall, persistent across sessions
     (preferences, style rules, domain knowledge, feedback). SQLite on disk.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import BASE_DIR
from .logging_setup import log

DEFAULT_MEMORY_DB = BASE_DIR / "workspace" / "agent_memory.db"


@dataclass
class PlanStep:
    id: str
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed
    result_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TraceStep:
    turn: int
    thought: str
    tool: str
    args: dict[str, Any]
    result: dict[str, Any]
    status: str = "success"  # success | error
    elapsed_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "thought": self.thought,
            "tool": self.tool,
            "args": self.args,
            "result": self.result,
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "timestamp": round(self.timestamp, 3),
        }


class WorkingMemory:
    """Tier 1: Short-term scratchpad and active task plan for a single agent run."""

    def __init__(self, session_id: str, goal: str = "") -> None:
        self.session_id = session_id
        self.goal = goal
        self.plan: list[PlanStep] = []
        self.scratchpad: dict[str, Any] = {}
        self.observations: list[str] = []
        self.step_count = 0
        self.tokens_used = 0

    def add_plan_step(self, step_id: str, description: str) -> None:
        self.plan.append(PlanStep(id=step_id, description=description))

    def update_plan_step(self, step_id: str, status: str, result_summary: str = "") -> None:
        for s in self.plan:
            if s.id == step_id:
                s.status = status
                if result_summary:
                    s.result_summary = result_summary
                break

    def record_observation(self, obs: str) -> None:
        self.observations.append(obs)
        if len(self.observations) > 30:
            self.observations = self.observations[-30:]

    def set_scratchpad(self, key: str, value: Any) -> None:
        self.scratchpad[key] = value

    def get_scratchpad(self, key: str, default: Any = None) -> Any:
        return self.scratchpad.get(key, default)

    def get_plan_summary(self) -> str:
        if not self.plan:
            return "No plan steps registered yet."
        lines = []
        for s in self.plan:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[✓]", "failed": "[!]"}.get(
                s.status, "[?]"
            )
            res = f" -> {s.result_summary}" if s.result_summary else ""
            lines.append(f"{marker} {s.id}: {s.description}{res}")
        return "\n".join(lines)


class CheckpointMemory:
    """Tier 2: Episodic trace of execution steps, serializable to JSONL audit logs."""

    def __init__(self, session_id: str, output_dir: Optional[Path] = None) -> None:
        self.session_id = session_id
        self.output_dir = output_dir
        self.traces: list[TraceStep] = []
        self._lock = threading.Lock()

    def record_turn(
        self,
        turn: int,
        thought: str,
        tool: str,
        args: dict[str, Any],
        result: dict[str, Any],
        status: str = "success",
        elapsed_ms: float = 0.0,
    ) -> TraceStep:
        step = TraceStep(
            turn=turn,
            thought=thought,
            tool=tool,
            args=args,
            result=result,
            status=status,
            elapsed_ms=elapsed_ms,
        )
        with self._lock:
            self.traces.append(step)
            if self.output_dir:
                try:
                    self.output_dir.mkdir(parents=True, exist_ok=True)
                    log_file = self.output_dir / "agent_trace.jsonl"
                    with log_file.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(step.to_dict()) + "\n")
                except Exception as e:
                    log.bind(task="agent").warning(f"failed to append trace log: {e}")
        return step

    def get_receipt(self) -> dict[str, Any]:
        with self._lock:
            return {
                "session_id": self.session_id,
                "total_turns": len(self.traces),
                "tools_used": list({t.tool for t in self.traces}),
                "has_errors": any(t.status == "error" for t in self.traces),
                "total_elapsed_ms": sum(t.elapsed_ms for t in self.traces),
                "steps": [t.to_dict() for t in self.traces],
            }


class HarnessMemory:
    """Tier 3: Long-term associative and semantic memory backed by persistent SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_MEMORY_DB
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._conn = conn
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    UNIQUE(namespace, key)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_ns ON agent_memories(namespace)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON agent_memories(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_tags ON agent_memories(tags)")
            conn.commit()
            self._seed_default_memories(conn)
        self._get_conn()

    def backend(self) -> str:
        """Memory is stored in the local SQLite file."""
        return "sqlite"

    def _mirror(self, namespace: str, key: str, value: str, tags: str, meta: str, now: float) -> None:
        del namespace, key, value, tags, meta, now

    def _hydrate_from_remote(self) -> None:
        return None

    def _seed_default_memories(self, conn: sqlite3.Connection) -> None:
        """Seed initial knowledge guidelines if table is empty."""
        cur = conn.execute("SELECT COUNT(*) AS c FROM agent_memories")
        row = cur.fetchone()
        if row and row["c"] > 0:
            return

        now = time.time()
        seeds = [
            # Preferences
            (
                "preferences",
                "default_pacing",
                json.dumps({
                    "landscape_wpm": 135.0,
                    "vertical_wpm": 125.0,
                    "target_dwell_min_sec": 1.2,
                    "rule": "Pacing should allow viewers to digest slides without dead silence."
                }),
                "pacing,timing,audio,speech",
            ),
            (
                "preferences",
                "density_guard",
                json.dumps({
                    "max_bullets": 5,
                    "max_words_per_bullet": 18,
                    "rule": "Prefer short punchy chips over dense paragraphs on slides."
                }),
                "density,bullets,readability",
            ),
            # Style rules
            (
                "style_rules",
                "ml_paper",
                json.dumps({
                    "preferred_families": ["treemap", "bento", "golden", "cascade"],
                    "themes": ["neon", "blueprint", "midnight"],
                    "guidance": "Highlight mathematical formulas, benchmark stats, and core architecture components."
                }),
                "ml,ai,research,paper,academic",
            ),
            (
                "style_rules",
                "executive_summary",
                json.dumps({
                    "preferred_families": ["bands", "skyline", "scatter"],
                    "themes": ["minimal", "editorial", "snow"],
                    "guidance": "Lead with key business metrics and high-level decision pillars."
                }),
                "business,executive,decision,strategy",
            ),
            (
                "style_rules",
                "how_to_tutorial",
                json.dumps({
                    "preferred_families": ["path", "cascade", "orbit"],
                    "themes": ["whiteboard", "chalkboard", "playful"],
                    "guidance": "Use ordered milestones with clear step numbers and actionable instructions."
                }),
                "tutorial,steps,guide,workflow",
            ),
            # Domain knowledge
            (
                "domain_knowledge",
                "slide_layout_taxonomy",
                json.dumps({
                    "families": [
                        "treemap", "orbit", "cascade", "masonry", "path",
                        "golden", "bands", "scatter", "slices", "skyline"
                    ],
                    "rule": "Every slide must have a distinct layout signature to avoid visual monotony."
                }),
                "taxonomy,layouts,geometry,engine",
            ),
        ]
        for ns, k, val, tags in seeds:
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_memories (namespace, key, value, tags, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, '{}', ?, ?)
                """,
                (ns, k, val, tags, now, now),
            )
        conn.commit()

    def store(
        self,
        key: str,
        value: Any,
        namespace: str = "general",
        tags: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Store or update a memory entry."""
        val_str = json.dumps(value) if not isinstance(value, str) else value
        meta_str = json.dumps(metadata or {})
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO agent_memories (namespace, key, value, tags, metadata, created_at, updated_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    value = excluded.value,
                    tags = excluded.tags,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (namespace, key, val_str, tags.lower(), meta_str, now, now),
            )
            conn.commit()
        self._mirror(namespace, key, val_str, tags.lower(), meta_str, now)

    def get(self, key: str, namespace: str = "general") -> Optional[Any]:
        """Fetch a specific memory item by key and namespace."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "SELECT value, metadata FROM agent_memories WHERE namespace = ? AND key = ?",
                (namespace, key),
            )
            row = cur.fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE agent_memories SET access_count = access_count + 1 WHERE namespace = ? AND key = ?",
                (namespace, key),
            )
            conn.commit()
            val = row["value"]
            try:
                return json.loads(val)
            except Exception:
                return val

    def recall(
        self,
        query: str,
        namespace: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Recall memories matching query tokens or tags, ranked by relevance."""
        tokens = [w.lower() for w in re.findall(r"[a-zA-Z0-9_-]{2,}", query or "")]
        with self._lock:
            conn = self._get_conn()
            clauses = []
            params: list[Any] = []
            if namespace:
                clauses.append("namespace = ?")
                params.append(namespace)
            if tags:
                tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
                for t in tag_list:
                    clauses.append("tags LIKE ?")
                    params.append(f"%{t}%")

            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = f"SELECT id, namespace, key, value, tags, metadata, updated_at, access_count FROM agent_memories {where}"
            cur = conn.execute(sql, params)
            rows = cur.fetchall()

            scored: list[tuple[float, dict[str, Any]]] = []
            now = time.time()
            for r in rows:
                score = 0.0
                text = f"{r['key']} {r['tags']} {r['value']}".lower()
                for tok in tokens:
                    if tok in r["key"].lower():
                        score += 3.0
                    elif tok in r["tags"].lower():
                        score += 2.0
                    elif tok in text:
                        score += 1.0

                # Slight recency bonus & usage frequency bonus
                age_days = (now - r["updated_at"]) / 86400.0
                recency_weight = 1.0 / (1.0 + math.log1p(max(0.0, age_days)))
                freq_bonus = min(1.0, r["access_count"] * 0.1)
                final_score = score * recency_weight + freq_bonus

                if not tokens or score > 0 or tags:
                    parsed_val = r["value"]
                    try:
                        parsed_val = json.loads(r["value"])
                    except Exception:
                        pass
                    item = {
                        "namespace": r["namespace"],
                        "key": r["key"],
                        "value": parsed_val,
                        "tags": r["tags"],
                        "score": round(final_score, 2),
                    }
                    scored.append((final_score, item))

            scored.sort(key=lambda x: x[0], reverse=True)
            results = [item for _, item in scored[:limit]]

            # Update access counts for recalled rows
            if results:
                for res in results:
                    conn.execute(
                        "UPDATE agent_memories SET access_count = access_count + 1 WHERE namespace = ? AND key = ?",
                        (res["namespace"], res["key"]),
                    )
                conn.commit()

            return results

    def list_namespaces(self) -> list[str]:
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("SELECT DISTINCT namespace FROM agent_memories ORDER BY namespace")
            return [r[0] for r in cur.fetchall()]

    def count(self) -> int:
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute("SELECT COUNT(*) FROM agent_memories")
            return int(cur.fetchone()[0])


# Global singleton instance for easy retrieval
_global_memory: Optional[HarnessMemory] = None
_mem_lock = threading.Lock()


def get_harness_memory() -> HarnessMemory:
    global _global_memory
    with _mem_lock:
        if _global_memory is None:
            _global_memory = HarnessMemory()
        return _global_memory
