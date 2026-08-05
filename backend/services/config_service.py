from sqlalchemy import text
from database import engine


class ConfigService:

    @staticmethod
    def get_company_config(company_id: str):

        query = """
        SELECT
            c.company_id,
            c.company_name,
            c.company_code,
            c.timezone,
            c.currency,
            c.date_format,
            c.sql_dialect,
            c.financial_year_start_month,
            c.week_start_day,
            c.default_calendar,
            c.locale,
            c.preferred_strategy
        FROM companies c
        WHERE c.company_id = :company_id
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "company_id": company_id
                }
            )

            row = result.fetchone()

            if not row:
                return None

            return dict(row._mapping)

    @staticmethod
    def update_company_config(
        company_id: str,
        timezone: str,
        currency: str,
        date_format: str,
        sql_dialect: str,
        financial_year_start_month: int = None,
        week_start_day: int = None,
        default_calendar: str = None,
        locale: str = None,
        preferred_strategy: str = None
    ):

        query = """
        UPDATE companies
        SET
            timezone = :timezone,
            currency = :currency,
            date_format = :date_format,
            sql_dialect = :sql_dialect,
            financial_year_start_month = :financial_year_start_month,
            week_start_day = :week_start_day,
            default_calendar = :default_calendar,
            locale = :locale,
            preferred_strategy = :preferred_strategy,
            updated_at = GETDATE()
        WHERE company_id = :company_id
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "company_id": company_id,
                    "timezone": timezone,
                    "currency": currency,
                    "date_format": date_format,
                    "sql_dialect": sql_dialect,
                    "financial_year_start_month": financial_year_start_month,
                    "week_start_day": week_start_day,
                    "default_calendar": default_calendar,
                    "locale": locale,
                    "preferred_strategy": preferred_strategy
                }
            )

        return True