"""FitAI memory logic. No database access; persistence is injected via protocols."""

from .change_detector import ChangeKind, DetectedChange, MemoryEntry, detect_changes
from .confirmation import (
    Action,
    ApplyResult,
    ConfirmationPolicy,
    Decision,
    MemoryWriter,
    apply_decisions,
    decide,
    decide_all,
)
from .continuity import ContinuityContext, format_continuity
from .extractor import (
    ExtractedFact,
    ExtractionResult,
    StatementType,
    Tense,
    TextCompleter,
    extract_facts,
)
from .history import HistoryPlan, HistoryRecord, build_history_record, prepare_history
from .summarizer import build_summary

__all__ = [
    "ExtractedFact",
    "ExtractionResult",
    "StatementType",
    "Tense",
    "TextCompleter",
    "extract_facts",
    "ContinuityContext",
    "format_continuity",
    "build_summary",
    "ChangeKind",
    "DetectedChange",
    "MemoryEntry",
    "detect_changes",
    "HistoryPlan",
    "HistoryRecord",
    "build_history_record",
    "prepare_history",
    "Action",
    "ApplyResult",
    "ConfirmationPolicy",
    "Decision",
    "MemoryWriter",
    "apply_decisions",
    "decide",
    "decide_all",
]
