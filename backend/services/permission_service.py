from sqlalchemy import text
from database import engine


class PermissionService:

    @staticmethod
    def get_permissions():

        query = """
        SELECT
            id,
            permission_name,
            description,
            category
        FROM permissions
        ORDER BY
            category,
            permission_name
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query)
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]

    @staticmethod
    def get_role_permissions(
        role_id: int
    ):

        query = """
        SELECT
            p.id,
            p.permission_name,
            p.description,
            p.category
        FROM role_permissions rp
        INNER JOIN permissions p
            ON rp.permission_id = p.id
        WHERE rp.role_id = :role_id
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "role_id": role_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]