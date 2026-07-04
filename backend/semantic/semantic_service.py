from database import engine
from sqlalchemy import text
import uuid
from fastapi import HTTPException
class SemanticService:

    @staticmethod
    def get_metrics(connection_id):
        query = """
        SELECT
            metric_id,
            metric_name,
            business_name,
            description,
            table_name,
            column_name,
            aggregation_type,source,
            is_active,
            created_at,
            updated_at

        FROM semantic_metrics
        WHERE connection_id = :connection_id
        ORDER BY business_name
        """

        with engine.connect() as conn:
            result = conn.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            )

            return [
                dict(row._mapping)
                for row in result.fetchall()
            ]

    @staticmethod
    def get_dimensions(connection_id):
        query = """
        SELECT
            dimension_id,
            dimension_name,
            business_name,
            description,
            table_name,
            column_name,
            source,
            is_active,
            created_at,
            updated_at
        FROM semantic_dimensions
        WHERE connection_id = :connection_id
        ORDER BY business_name
        """
        with engine.connect() as conn:
            result = conn.execute(text(query),{"connection_id": connection_id})
            return [dict(row._mapping) for row in result.fetchall()]

    @staticmethod
    def create_metric(connection_id, data, user):

        with engine.begin() as conn:

            duplicate = conn.execute(
                text("""
                    SELECT 1
                    FROM semantic_metrics
                    WHERE connection_id = :connection_id
                      AND LOWER(metric_name) = LOWER(:metric_name)
                """),
                {
                    "connection_id": connection_id,
                    "metric_name": data["metric_name"]
                }
            ).fetchone()

            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Metric already exists."
                )

            metric_id = str(uuid.uuid4())

            conn.execute(
                text("""
                    INSERT INTO semantic_metrics
                    (
                        metric_id,
                        connection_id,
                        metric_name,
                        business_name,
                        description,
                        table_name,
                        column_name,
                        aggregation_type,
                        source,
                        is_active,
                        created_by,
                        updated_by
                    )
                    VALUES
                    (
                        :metric_id,
                        :connection_id,
                        :metric_name,
                        :business_name,
                        :description,
                        :table_name,
                        :column_name,
                        :aggregation_type,
                        'MANUAL',
                        1,
                        :created_by,
                        :updated_by
                    )
                """),
                {
                    "metric_id": metric_id,
                    "connection_id": connection_id,
                    "metric_name": data["metric_name"],
                    "business_name": data["business_name"],
                    "description": data.get("description"),
                    "table_name": data["table_name"],
                    "column_name": data["column_name"],
                    "aggregation_type": data["aggregation_type"],
                    "created_by": user["employee_id"],
                    "updated_by": user["employee_id"]
                }
            )

        return {
            "message": "Semantic metric created successfully.",
            "metric_id": metric_id
        }

    @staticmethod
    def update_metric(metric_id, data, user):

        with engine.begin() as conn:

            existing = conn.execute(
                text("""
                    SELECT connection_id
                    FROM semantic_metrics
                    WHERE metric_id = :metric_id
                """),
                {
                    "metric_id": metric_id
                }
            ).fetchone()

            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail="Metric not found."
                )

            connection_id = existing.connection_id

            duplicate = conn.execute(
                text("""
                    SELECT 1
                    FROM semantic_metrics
                    WHERE connection_id = :connection_id
                      AND LOWER(metric_name) = LOWER(:metric_name)
                      AND metric_id <> :metric_id
                """),
                {
                    "connection_id": connection_id,
                    "metric_name": data["metric_name"],
                    "metric_id": metric_id
                }
            ).fetchone()

            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Metric already exists."
                )

            conn.execute(
                text("""
                    UPDATE semantic_metrics
                    SET
                        metric_name = :metric_name,
                        business_name = :business_name,
                        description = :description,
                        table_name = :table_name,
                        column_name = :column_name,
                        aggregation_type = :aggregation_type,
                        is_active = :is_active,
                        updated_by = :updated_by,
                        updated_at = GETDATE()
                    WHERE metric_id = :metric_id
                """),
                {
                    "metric_id": metric_id,
                    "metric_name": data["metric_name"],
                    "business_name": data["business_name"],
                    "description": data.get("description"),
                    "table_name": data["table_name"],
                    "column_name": data["column_name"],
                    "aggregation_type": data["aggregation_type"],
                    "is_active": data.get("is_active", True),
                    "updated_by": user["employee_id"]
                }
            )

        return {
            "message": "Semantic metric updated successfully."
        }

    @staticmethod
    def delete_metric(metric_id):

        with engine.begin() as conn:

            existing = conn.execute(
                text("""
                    SELECT source
                    FROM semantic_metrics
                    WHERE metric_id = :metric_id
                """),
                {
                    "metric_id": metric_id
                }
            ).fetchone()

            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail="Metric not found."
                )

            if existing.source != "MANUAL":
                raise HTTPException(
                    status_code=400,
                    detail="AUTO generated metrics cannot be deleted."
                )

            conn.execute(
                text("""
                    DELETE FROM semantic_metrics
                    WHERE metric_id = :metric_id
                """),
                {
                    "metric_id": metric_id
                }
            )

        return {
            "message": "Semantic metric deleted successfully."
        }

    @staticmethod
    def create_dimension(connection_id, data, user):

        with engine.begin() as conn:

            duplicate = conn.execute(
                text("""
                    SELECT 1
                    FROM semantic_dimensions
                    WHERE connection_id = :connection_id
                      AND LOWER(dimension_name) = LOWER(:dimension_name)
                """),
                {
                    "connection_id": connection_id,
                    "dimension_name": data["dimension_name"]
                }
            ).fetchone()

            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Dimension already exists."
                )

            dimension_id = str(uuid.uuid4())

            conn.execute(
                text("""
                    INSERT INTO semantic_dimensions
                    (
                        dimension_id,
                        connection_id,
                        dimension_name,
                        business_name,
                        description,
                        table_name,
                        column_name,
                        source,
                        is_active,
                        created_by,
                        updated_by
                    )
                    VALUES
                    (
                        :dimension_id,
                        :connection_id,
                        :dimension_name,
                        :business_name,
                        :description,
                        :table_name,
                        :column_name,
                        'MANUAL',
                        1,
                        :created_by,
                        :updated_by
                    )
                """),
                {
                    "dimension_id": dimension_id,
                    "connection_id": connection_id,
                    "dimension_name": data["dimension_name"],
                    "business_name": data["business_name"],
                    "description": data.get("description"),
                    "table_name": data["table_name"],
                    "column_name": data["column_name"],
                    "created_by": user["employee_id"],
                    "updated_by": user["employee_id"]
                }
            )

        return {
            "message": "Semantic dimension created successfully.",
            "dimension_id": dimension_id
        }


    @staticmethod
    def update_dimension(dimension_id, data, user):

        with engine.begin() as conn:

            existing = conn.execute(
                text("""
                    SELECT connection_id
                    FROM semantic_dimensions
                    WHERE dimension_id = :dimension_id
                """),
                {
                    "dimension_id": dimension_id
                }
            ).fetchone()

            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail="Dimension not found."
                )

            connection_id = existing.connection_id

            duplicate = conn.execute(
                text("""
                    SELECT 1
                    FROM semantic_dimensions
                    WHERE connection_id = :connection_id
                      AND LOWER(dimension_name) = LOWER(:dimension_name)
                      AND dimension_id <> :dimension_id
                """),
                {
                    "connection_id": connection_id,
                    "dimension_name": data["dimension_name"],
                    "dimension_id": dimension_id
                }
            ).fetchone()

            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail="Dimension already exists."
                )

            conn.execute(
                text("""
                    UPDATE semantic_dimensions
                    SET
                        dimension_name = :dimension_name,
                        business_name = :business_name,
                        description = :description,
                        table_name = :table_name,
                        column_name = :column_name,
                        is_active = :is_active,
                        updated_by = :updated_by,
                        updated_at = GETDATE()
                    WHERE dimension_id = :dimension_id
                """),
                {
                    "dimension_id": dimension_id,
                    "dimension_name": data["dimension_name"],
                    "business_name": data["business_name"],
                    "description": data.get("description"),
                    "table_name": data["table_name"],
                    "column_name": data["column_name"],
                    "is_active": data.get("is_active", True),
                    "updated_by": user["employee_id"]
                }
            )

        return {
            "message": "Semantic dimension updated successfully."
        }

    @staticmethod
    def delete_dimension(dimension_id):

        with engine.begin() as conn:

            existing = conn.execute(
                text("""
                    SELECT source
                    FROM semantic_dimensions
                    WHERE dimension_id = :dimension_id
                """),
                {
                    "dimension_id": dimension_id
                }
            ).fetchone()

            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail="Dimension not found."
                )

            if existing.source != "MANUAL":
                raise HTTPException(
                    status_code=400,
                    detail="AUTO generated dimensions cannot be deleted."
                )

            conn.execute(
                text("""
                    DELETE FROM semantic_dimensions
                    WHERE dimension_id = :dimension_id
                """),
                {
                    "dimension_id": dimension_id
                }
            )

        return {
            "message": "Semantic dimension deleted successfully."
        }