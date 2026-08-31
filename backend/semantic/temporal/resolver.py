import datetime
import calendar
from typing import Optional, List, Tuple, Dict, Any

from .enums import TimeStrategyType, CalendarType, Granularity, TimeIntentType
from .models import (
    BaseTimeIntent,
    TimeCapability,
    TimeSettings,
    CalculatedDateRange,
    ResolvedTimePlan,
    LastNDaysIntent,
    LastNWeeksIntent,
    LastNMonthsIntent,
    LastNYearsIntent,
    CurrentDayIntent,
    CurrentWeekIntent,
    CurrentMonthIntent,
    CurrentYearIntent,
    PreviousDayIntent,
    PreviousWeekIntent,
    PreviousMonthIntent,
    PreviousYearIntent,
    DateRangeIntent,
    YearRangeIntent,
    MonthRangeIntent,
    YearComparisonIntent,
    MonthComparisonIntent,
    GrowthIntent,
    TrendIntent,
    RunningTotalIntent,
    YTDIntent,
    MTDIntent,
    QTDIntent,
    FiscalYTDIntent,
)
from .exceptions import StrategyResolutionError
from .date_calculator import DateCalculator

class TimeStrategyResolver:
    """
    Executes a chosen or dynamically selected TimeStrategyType against
    a datasource's TimeCapability and temporal intent.
    """
    def resolve(
        self,
        intent: Any = None,
        capability: Any = None,
        settings: Any = None,
        connection_id: Optional[str] = None,
        strategy: Optional[TimeStrategyType] = None
    ) -> ResolvedTimePlan:
        # Handle positional or type-dispatched signatures
        if isinstance(intent, TimeStrategyType):
            strategy = intent
            intent = capability
            capability = settings
            settings = connection_id if isinstance(connection_id, TimeSettings) else None
            # If connection_id was actually connection_id string, we handle it if needed
            if isinstance(connection_id, str):
                actual_conn_id = connection_id
            else:
                actual_conn_id = None
        else:
            actual_conn_id = connection_id

        # Determine the reference date
        ref_date = getattr(intent, "reference_date", None) or datetime.date.today()
        
        # Initialize default settings if not provided
        if settings is None or not isinstance(settings, TimeSettings):
            settings = TimeSettings()

        # If capability is not provided, discover/retrieve it
        if capability is None or not isinstance(capability, TimeCapability):
            if actual_conn_id:
                from .capability_cache import TimeResolutionCache
                cached_entry = TimeResolutionCache.get(actual_conn_id)
                if cached_entry:
                    capability = cached_entry.capability
                else:
                    capability = self._discover_capability(actual_conn_id)
                    TimeResolutionCache.put(actual_conn_id, capability)
            else:
                capability = TimeCapability()

        # If strategy was not explicitly passed, delegate selection to Strategy Selector
        if strategy is None:
            from .strategy_selector import TimeStrategySelector
            selector = TimeStrategySelector()
            selection = selector.select(intent, capability, settings, actual_conn_id)
            strategy = selection.strategy
        
        # Instantiate DateCalculator
        calculator = DateCalculator(settings)
        calc_range = calculator.calculate(intent)

        # Determine available bounds from Capability
        min_date = None
        max_date = None
        available_years = None
        
        if capability.available_date_range:
            min_date = capability.available_date_range.start_date
            max_date = capability.available_date_range.end_date
            available_years = max_date.year - min_date.year + 1
        elif capability.available_year_range:
            min_date = datetime.date(capability.available_year_range.min_year, 1, 1)
            max_date = datetime.date(capability.available_year_range.max_year, 12, 31)
            available_years = capability.available_year_range.max_year - capability.available_year_range.min_year + 1
        
        start_date = calc_range.start_date
        end_date = calc_range.end_date
        is_partial = False
        warnings = []
        requested_years = None
        
        if isinstance(intent, LastNYearsIntent):
            requested_years = intent.count
        elif start_date and end_date:
            requested_years = end_date.year - start_date.year + 1

        if start_date and min_date and start_date < min_date:
            start_date = min_date
            is_partial = True
            if available_years is None and end_date:
                available_years = end_date.year - min_date.year + 1
            if requested_years and available_years:
                warnings.append(f"Requested {requested_years} years, but only {available_years} years are available.")

        if end_date and max_date and end_date > max_date:
            end_date = max_date
            is_partial = True

        plan = self._resolve_with_strategy(
            strategy_type=strategy,
            intent=intent,
            capability=capability,
            calc_range=calc_range,
            start_date=start_date,
            end_date=end_date,
            ref_date=ref_date,
            is_partial=is_partial,
            requested_years=requested_years,
            available_years=available_years,
            warnings=warnings
        )
        
        if plan:
            return plan

        raise StrategyResolutionError(
            f"Could not execute strategy '{strategy}' for intent '{intent.intent_type}' "
            f"on schema capability."
        )

    def _discover_capability(self, connection_id: str) -> TimeCapability:
        """
        Build the capability from configuration (Gate 2 Step 11a).

        This returned an empty TimeCapability until now, which is why nothing
        downstream could resolve a period from it and the column names had to
        be hardcoded in two other modules instead.

        date_columns is deliberately left empty even though two tables are
        configured DATE_COLUMN. TimeCapability is scoped to a CONNECTION while
        the configuration is scoped to a TABLE, so publishing Order Pending's
        DocDate here would offer it for a query against Sales - a table whose
        only date-like column is an ETL load timestamp that must never be used
        for analysis. Handing a per-table fact to a per-connection consumer is
        how a silently wrong grouping gets built, so it waits for the capability
        to become table-aware.
        """
        from .snapshot_config import SnapshotConfigLoader

        config = SnapshotConfigLoader.for_connection(connection_id)

        return TimeCapability(
            snapshot_mapping=config.offset_to_column("VALUE"),
            snapshot_bindings=list(config.bindings),
        )

    def _resolve_with_strategy(
        self,
        strategy_type: TimeStrategyType,
        intent: BaseTimeIntent,
        capability: TimeCapability,
        calc_range: CalculatedDateRange,
        start_date: Optional[datetime.date],
        end_date: Optional[datetime.date],
        ref_date: datetime.date,
        is_partial: bool,
        requested_years: Optional[int],
        available_years: Optional[int],
        warnings: List[str]
    ) -> Optional[ResolvedTimePlan]:
        if strategy_type == TimeStrategyType.SNAPSHOT:
            snapshot_mapping = capability.snapshot_mapping
            if snapshot_mapping:
                if isinstance(intent, LastNYearsIntent):
                    req_years = intent.count
                    avail_years = len(snapshot_mapping)
                    if req_years > avail_years:
                        mapped_cols = [snapshot_mapping[i] for i in range(avail_years) if i in snapshot_mapping]
                        warns = [f"Requested {req_years} years, but only {avail_years} years are available."]
                        return ResolvedTimePlan(
                            strategy=TimeStrategyType.SNAPSHOT,
                            grouping=Granularity.YEAR,
                            snapshot_columns=mapped_cols,
                            reference_date=ref_date,
                            is_partial=True,
                            requested_years=req_years,
                            available_years=avail_years,
                            warnings=warns
                        )
                
                mapped_cols = self._map_to_snapshot_columns(
                    intent, snapshot_mapping, ref_date,
                    capability=capability, warnings=warnings
                )
                if mapped_cols:
                    grouping = Granularity.YEAR
                    if isinstance(intent, (LastNMonthsIntent, PreviousMonthIntent, CurrentMonthIntent)):
                        grouping = Granularity.MONTH
                    return ResolvedTimePlan(
                        strategy=TimeStrategyType.SNAPSHOT,
                        grouping=grouping,
                        snapshot_columns=mapped_cols,
                        reference_date=ref_date
                    )

        elif strategy_type == TimeStrategyType.CALENDAR_DIMENSION:
            if capability.calendar_tables:
                date_col = capability.default_date_column or (capability.date_columns[0] if capability.date_columns else None)
                return ResolvedTimePlan(
                    strategy=TimeStrategyType.CALENDAR_DIMENSION,
                    date_column=date_col,
                    grouping=calc_range.granularity,
                    start_date=start_date,
                    end_date=end_date,
                    calendar_table=capability.calendar_tables[0],
                    is_partial=is_partial,
                    requested_years=requested_years,
                    available_years=available_years,
                    warnings=warnings
                )

        elif strategy_type == TimeStrategyType.FISCAL:
            if intent.intent_type == TimeIntentType.FISCAL_YTD and capability.supports_fiscal_calendar:
                date_col = capability.default_date_column or (capability.date_columns[0] if capability.date_columns else None)
                return ResolvedTimePlan(
                    strategy=TimeStrategyType.FISCAL,
                    date_column=date_col,
                    start_date=start_date,
                    end_date=end_date,
                    reference_date=ref_date,
                    is_partial=is_partial,
                    requested_years=requested_years,
                    available_years=available_years,
                    warnings=warnings
                )

        elif strategy_type == TimeStrategyType.DATE_COLUMN:
            if capability.date_columns:
                date_col = capability.default_date_column or capability.date_columns[0]
                return ResolvedTimePlan(
                    strategy=TimeStrategyType.DATE_COLUMN,
                    date_column=date_col,
                    grouping=calc_range.granularity,
                    start_date=start_date,
                    end_date=end_date,
                    reference_date=ref_date,
                    is_partial=is_partial,
                    requested_years=requested_years,
                    available_years=available_years,
                    warnings=warnings
                )
        return None

    def _map_to_snapshot_columns(
        self,
        intent: BaseTimeIntent,
        snapshot_mapping: Dict[int, str],
        ref_date: datetime.date,
        capability: Any = None,
        warnings: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        if isinstance(intent, CurrentYearIntent):
            if 0 in snapshot_mapping:
                return [snapshot_mapping[0]]
                
        elif isinstance(intent, PreviousYearIntent):
            if 1 in snapshot_mapping:
                return [snapshot_mapping[1]]
                
        elif isinstance(intent, LastNYearsIntent):
            mapped = []
            for i in range(intent.count):
                if i in snapshot_mapping:
                    mapped.append(snapshot_mapping[i])
                else:
                    return None
            return mapped
            
        elif getattr(intent, "intent_type", None) in ("PPY", TimeIntentType.PPY):
            if 2 in snapshot_mapping:
                return [snapshot_mapping[2]]
                
        elif getattr(intent, "intent_type", None) in ("PPPY", TimeIntentType.PPPY):
            if 3 in snapshot_mapping:
                return [snapshot_mapping[3]]
                
        elif getattr(intent, "intent_type", None) in ("PPPPY", TimeIntentType.PPPPY):
            if 4 in snapshot_mapping:
                return [snapshot_mapping[4]]
                
        elif isinstance(intent, YearComparisonIntent):
            start_offset = ref_date.year - intent.start_year
            end_offset = ref_date.year - intent.end_year

            offsets = [start_offset, end_offset]

            if any(offset < 0 for offset in offsets):
                return None

            # Step 11b: a comparison involving the running period resolves the
            # other periods to their to-date columns, so five months are not
            # measured against twelve. Needs the scope-aware bindings; without
            # them this falls through to the pre-11b behaviour below.
            bindings = getattr(capability, "snapshot_bindings", None)

            if bindings:
                from .snapshot_config import SnapshotConfig

                columns, comparison_warnings = SnapshotConfig.from_bindings(
                    bindings
                ).comparison_columns(offsets)

                if warnings is not None:
                    warnings.extend(comparison_warnings)

                if columns:
                    return columns

            mapped = []
            for offset in offsets:
                if offset in snapshot_mapping:
                    mapped.append(snapshot_mapping[offset])
                else:
                    return None
            return mapped
            
        return None
