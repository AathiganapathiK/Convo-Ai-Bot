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
            c.sql_dialect
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
        sql_dialect: str
    ):

        query = """
        UPDATE companies
        SET
            timezone = :timezone,
            currency = :currency,
            date_format = :date_format,
            sql_dialect = :sql_dialect,
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
                    "sql_dialect": sql_dialect
                }
            )

        return True


    