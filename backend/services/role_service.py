
from sqlalchemy import text
from database import engine


class RoleService:

    @staticmethod
    def get_company_roles(company_id: str):

        query = """
        SELECT
            id,
            role_name,
            description,
            is_active,
            is_system_role,
            created_at
        FROM roles
        WHERE company_id = :company_id
        ORDER BY role_name
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "company_id": company_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]

    @staticmethod
    def get_role(role_id: int):

        query = """
        SELECT *
        FROM roles
        WHERE id = :role_id
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "role_id": role_id
                }
            )

            row = result.fetchone()

            return (
                dict(row._mapping)
                if row
                else None
            )

    @staticmethod
    def create_role(
        company_id: str,
        role_name: str,
        description: str
    ):

        query = """
        INSERT INTO roles
        (
            company_id,
            role_name,
            description,
            is_active,
            is_system_role
        )
        VALUES
        (
            :company_id,
            :role_name,
            :description,
            1,
            0
        )
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "company_id": company_id,
                    "role_name": role_name,
                    "description": description
                }
            )

        return True

    @staticmethod
    def delete_role(role_id: int):

        query = """
        DELETE FROM roles
        WHERE
            id = :role_id
            AND is_system_role = 0
        """

        with engine.begin() as connection:

            result = connection.execute(
                text(query),
                {
                    "role_id": role_id
                }
            )

        return result.rowcount > 0