import time
import logging
import datetime
import threading
from typing import Optional, Any

from .detector import TemporalDetector
from .time_resolver import TimeResolver
from .context_builder import TimeContextBuilder
from .temporal_prompt_formatter import TemporalPromptFormatter
from .models import TimeSettings, TimeResolutionResult, BaseTimeIntent
from .exceptions import TemporalException
from core.logger import debug_print as print

logger = logging.getLogger("TemporalPipeline")


class TemporalPipeline:
    """Orchestrates temporal resolution, context mapping, text formatting, and production telemetry."""

    _thread_local = threading.local()

    @classmethod
    def get_last_resolution(cls) -> Optional[TimeResolutionResult]:
        return getattr(cls._thread_local, "last_resolution", None)

    @classmethod
    def get_last_intent(cls) -> Optional[BaseTimeIntent]:
        return getattr(cls._thread_local, "last_intent", None)

    @classmethod
    def clear_last_result(cls):
        cls._thread_local.last_resolution = None
        cls._thread_local.last_intent = None

    def __init__(
        self,
        detector: Optional[TemporalDetector] = None,
        time_resolver: Optional[TimeResolver] = None,
        context_builder: Optional[TimeContextBuilder] = None,
        temporal_formatter: Optional[TemporalPromptFormatter] = None
    ):
        self.detector = detector or TemporalDetector()
        self.time_resolver = time_resolver or TimeResolver(detector=self.detector)
        self.context_builder = context_builder or TimeContextBuilder()
        self.temporal_formatter = temporal_formatter or TemporalPromptFormatter()

    def build(
        self,
        question: str,
        connection_id: Optional[str] = None,
        settings: Optional[TimeSettings] = None,
        style: str = "llm",
        reference_date: Optional[datetime.date] = None
    ) -> str:
        self.clear_last_result()
        start_time = time.time()

        if reference_date is None:
            reference_date = datetime.date.today()

        # Phase 2.1.7.3: Skip Temporal Resolution if Not Needed
        try:
            intent = self.detector.detect(question, reference_date=reference_date)
            if not intent:
                return ""
        except TemporalException as te:
            print(f"[Temporal] Expected exception in detection: {te}")
            return ""

        self._thread_local.last_intent = intent

        # Phase 2.1.7.2: Better Exception Handling (Catch only TemporalException)
        try:
            time_resolution = self.time_resolver.resolve(
                question=question,
                connection_id=connection_id,
                settings=settings,
                reference_date=reference_date
            )

            self._thread_local.last_resolution = time_resolution

            if not time_resolution.resolved:
                return ""

            active_settings = settings or TimeSettings()
            time_context = self.context_builder.build(time_resolution, active_settings)
            formatted_block = self.temporal_formatter.format(time_context, style=style)

            execution_time_ms = round((time.time() - start_time) * 1000, 2)

            # Phase 2.1.7.9: Production Logging
            intent_type = intent.__class__.__name__
            strategy_name = time_resolution.plan.strategy.value if (time_resolution.plan and time_resolution.plan.strategy) else "None"
            warnings_list = time_resolution.plan.warnings if time_resolution.plan else []
            is_partial = time_resolution.plan.is_partial if time_resolution.plan else False

            print(
                f"[Temporal]\n"
                f"  Intent        : {intent_type}\n"
                f"  Strategy      : {strategy_name}\n"
                f"  Execution Time: {execution_time_ms}ms\n"
                f"  Partial       : {is_partial}\n"
                f"  Warnings      : {warnings_list}"
            )

            return formatted_block

        except TemporalException as te:
            print(f"[Temporal] Expected exception in pipeline execution: {te}")
            return ""
