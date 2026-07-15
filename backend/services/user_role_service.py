from sqlalchemy import text
from database import engine


class UserRoleService:

    @staticmethod
    def get_user_roles(
        employee_id: str,
        company_id: str
    ):

        query = """
        SELECT
            r.id,
            r.role_name,
            r.is_system_role
        FROM user_roles ur

        INNER JOIN roles r
            ON ur.role_id = r.id

        WHERE
            ur.employee_id = :employee_id
            AND
            ur.company_id = :company_id
            AND
            r.is_active = 1
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "employee_id": employee_id,
                    "company_id": company_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]


    @staticmethod
    def get_role_names(
        employee_id: str,
        company_id: str
    ):

        roles = UserRoleService.get_user_roles(
            employee_id,
            company_id
        )

        return [
            role["role_name"]
            for role in roles
        ]

    @staticmethod
    def assign_role(
        company_id: str,
        employee_id: str,
        role_id: int
    ):

        query = """
        IF NOT EXISTS
        (
            SELECT 1
            FROM user_roles
            WHERE
                employee_id = :employee_id
                AND role_id = :role_id
        )
        INSERT INTO user_roles
        (
            company_id,
            employee_id,
            role_id
        )
        VALUES
        (
            :company_id,
            :employee_id,
            :role_id
        )
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "company_id": company_id,
                    "employee_id": employee_id,
                    "role_id": role_id
                }
            )

        return True

    @staticmethod
    def remove_role(
        employee_id: str,
        role_id: int
    ):

        query = """
        DELETE
        FROM user_roles
        WHERE
            employee_id = :employee_id
            AND role_id = :role_id
        """

        with engine.begin() as connection:

            connection.execute(
                text(query),
                {
                    "employee_id": employee_id,
                    "role_id": role_id
                }
            )

        return True

    
    @staticmethod
    def get_user_role_details(
        employee_id: str,
        company_id: str
    ):

        query = """
        SELECT
            r.id,
            r.role_name,
            r.description
        FROM user_roles ur
        INNER JOIN roles r
            ON ur.role_id = r.id
        WHERE
            ur.employee_id = :employee_id
            AND ur.company_id = :company_id
        """

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "employee_id": employee_id,
                    "company_id": company_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ] 