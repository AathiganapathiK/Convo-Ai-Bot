from sqlalchemy import text
from database import engine


class DBService:

    @staticmethod
    def get_engine():
        return engine

    @staticmethod
    def execute_query(query: str, params: dict = None):
        with engine.connect() as connection:
            result = connection.execute(
                text(query),
                params or {}
            )
            return result

    @staticmethod
    def execute_transaction(query: str, params: dict = None):
        with engine.begin() as connection:
            result = connection.execute(
                text(query),
                params or {}
            )
            return result