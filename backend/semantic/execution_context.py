from typing import Optional, Dict, Any
from semantic.temporal.models import TimeCapability, TimeSettings


class SemanticExecutionContext:
    """Holds and shares connection, company settings, capabilities, schema, and cache details across the semantic engine components."""

    def __init__(
        self,
        connection_id: Optional[str] = None,
        company_id: Optional[str] = None,
        settings: Optional[TimeSettings] = None
    ):
        self.connection_id = connection_id
        self.company_id = company_id
        
        # Load connection
        from services.connection_service import ConnectionService
        if connection_id:
            self.connection = ConnectionService.get_connection(connection_id)
        elif company_id:
            self.connection = ConnectionService.get_active_connection(company_id)
        else:
            self.connection = ConnectionService.get_active_connection_global()
            
        if self.connection:
            self.connection_id = self.connection.get("connection_id")
            
        # Load company config
        from services.config_service import ConfigService
        self.company = None
        if self.company_id:
            self.company = ConfigService.get_company_config(self.company_id)
        elif self.connection:
            conn_company_id = self.connection.get("company_id")
            if conn_company_id:
                self.company_id = conn_company_id
                self.company = ConfigService.get_company_config(conn_company_id)

        # Resolve TimeSettings from company configuration (Phase 2.1.7.4)
        from semantic.temporal.models import TimeSettings
        from semantic.temporal.enums import CalendarType
        
        if settings:
            self.settings = settings
        elif self.company:
            fy_month = self.company.get("financial_year_start_month")
            if fy_month is None:
                fy_month = 4
                
            cal_type_str = self.company.get("default_calendar")
            cal_type = CalendarType.CALENDAR
            if cal_type_str:
                if cal_type_str.lower() == "fiscal":
                    cal_type = CalendarType.FISCAL
                    
            ws_day = self.company.get("week_start_day")
            if ws_day is None:
                ws_day = 0
                
            loc = self.company.get("locale") or "en_US"
            
            self.settings = TimeSettings(
                financial_year_start_month=fy_month,
                default_calendar=cal_type,
                timezone=self.company.get("timezone") or "UTC",
                week_start_day=ws_day,
                locale=loc
            )
        else:
            self.settings = TimeSettings()

        # Load capability from Cache
        from semantic.temporal.capability_cache import TimeResolutionCache
        self.cache = TimeResolutionCache
        self.capability = None
        if self.connection_id:
            cached_entry = TimeResolutionCache.get(self.connection_id)
            if cached_entry:
                self.capability = cached_entry.capability

        self.schema = None
