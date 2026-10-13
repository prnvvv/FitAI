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
from .extractor import (
                           ExtractedFact,
                           ExtractionResult,
                           StatementType,
                           Tense,
                           TextCompleter,
                           extract_facts,
)
from .history import HistoryPlan, HistoryRecord, build_history_record, prepare_history

__all__ = [
    "ExtractedFact", "ExtractionResult", "StatementType", "Tense", "TextCompleter", "extract_facts",
    "ChangeKind", "DetectedChange", "MemoryEntry", "detect_changes",
    "HistoryPlan", "HistoryRecord", "build_history_record", "prepare_history",
    "Action", "ApplyResult", "ConfirmationPolicy", "Decision", "MemoryWriter",
    "apply_decisions", "decide", "decide_all",
]
