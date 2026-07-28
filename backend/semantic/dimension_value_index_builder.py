from sqlalchemy.engine import result
from semantic import dimension_value_resolver
from sqlalchemy import dialects
from services.connection_service import ConnectionService
from services.database_connection_factory import DatabaseConnectionFactory
from sqlalchemy import text
from database import engine
import re
import time

class DimensionValueIndexBuilder:
    MAX_INDEX_VALUES = 5000

    @staticmethod
    def _load_dimension(connection_id: str, dimension_id: str):
        """
        Load an active semantic dimension from the platform database.
        """

        query = """
        SELECT
            dimension_id,
            connection_id,
            dimension_name, 
            business_name,
            table_name,
            column_name,
            synonyms,
            source,
            is_active
        FROM semantic_dimensions
        WHERE
            connection_id = :connection_id
            AND dimension_id = :dimension_id
            AND is_active = 1
        """

        with engine.connect() as conn:
            result = conn.execute(
                text(query),
                {
                    "connection_id": connection_id,
                    "dimension_id": dimension_id
                }
            )

            row = result.fetchone()

            if not row:
                raise ValueError(
                    f"Semantic dimension '{dimension_id}' not found or inactive."
                )

            return dict(row._mapping)


    @staticmethod
    def build_dimension(
        connection_id: str,
        dimension_id: str
    ):
        """
        Build or rebuild the value index
        for a single semantic dimension.
        """

        # Load semantic metadata
        dimension = DimensionValueIndexBuilder._load_dimension(
            connection_id,
            dimension_id
        )
        print(
            f"Building: {dimension['table_name']}.{dimension['column_name']}"
        )

        # Load datasource metadata
        connection = ConnectionService.get_connection(
            connection_id
        )

        if not connection:
            raise ValueError(
                f"Datasource '{connection_id}' not found."
            )

        # Create source engine
        source_engine = (
            DatabaseConnectionFactory
            .create_engine_for_connection(connection)
        )

        DimensionValueIndexBuilder._validate_dimension_mapping(
            source_engine,
            dimension["table_name"],
            dimension["column_name"]
        )

        # Fetch values from source database
        values = (
            DimensionValueIndexBuilder
            ._fetch_distinct_values(
                source_engine,
                dimension["table_name"],
                dimension["column_name"]
            )
        )

        print(
            f"Fetched {len(values)} distinct values from "
            f"{dimension['table_name']}.{dimension['column_name']}"
        )

        if (
            DimensionValueIndexBuilder.MAX_INDEX_VALUES is not None
            and len(values) > DimensionValueIndexBuilder.MAX_INDEX_VALUES
        ):

            print(
                f"[SKIPPED] High cardinality "
                f"({len(values)} values, "
                f"limit={DimensionValueIndexBuilder.MAX_INDEX_VALUES})"
            )

            return {
                "dimension_id": dimension_id,
                "business_name": dimension["business_name"],
                "indexed_values": len(values),
                "status": "SKIPPED_HIGH_CARDINALITY"
            }

        # Nothing to index
        if not values:

            print(
                f"[SKIPPED] No values found for "
                f"{dimension['table_name']}.{dimension['column_name']}"
            )

            return {
                "dimension_id": dimension_id,
                "business_name": dimension["business_name"],
                "indexed_values": 0,
                "status": "SKIPPED_EMPTY"
            }

        # Replace index
        DimensionValueIndexBuilder._replace_dimension_values(
            connection_id,
            dimension_id,
            values
        )

        print(
            f"Inserted {len(values)} values into dimension_value_index"
        )

        return {
            "dimension_id": dimension_id,
            "business_name": dimension["business_name"],
            "indexed_values": len(values),
            "status": "SUCCESS"
        }

    @staticmethod
    def build_all(connection_id: str):
        """
        Build or rebuild the value index
        for all active semantic dimensions.
        """

        query = """
        SELECT
            dimension_id
        FROM semantic_dimensions
        WHERE
            connection_id = :connection_id
            AND is_active = 1
        ORDER BY business_name
        """
        

        with engine.connect() as conn:

            result = conn.execute(
                text(query),
                {
                    "connection_id": connection_id
                }
            )

            dimensions = [
                row._mapping["dimension_id"]
                for row in result.fetchall()
            ]

            print(f"[DIMENSION VALUE INDEX] Found {len(dimensions)} dimensions")

        summary = []
        errors = []
        skipped = []

        total = len(dimensions)

        for index, dimension_id in enumerate(dimensions, start=1):

            print("\n" + "=" * 80)
            print(f"[{index}/{total}] Processing Dimension: {dimension_id}")

            start = time.time()

            try:

                result = DimensionValueIndexBuilder.build_dimension(
                    connection_id,
                    dimension_id
                )

                elapsed = time.time() - start

                if result.get("status") in (
                    "SKIPPED_EMPTY",
                    "SKIPPED_HIGH_CARDINALITY"
                ):

                    if result["status"] == "SKIPPED_EMPTY":

                        print(
                            f"[SKIPPED] {result['business_name']} "
                            f"(No values found)"
                        )

                    else:

                        print(
                            f"[SKIPPED] {result['business_name']} "
                            f"-> {result['indexed_values']} values "
                            f"(High Cardinality)"
                        )

                    skipped.append(result)

                else:

                    print(
                        f"[SUCCESS] {result['business_name']} "
                        f"-> {result['indexed_values']} values "
                        f"({elapsed:.2f} sec)"
                    )

                    summary.append(result)

            except Exception as ex:

                elapsed = time.time() - start

                import traceback
                traceback.print_exc()

                print(
                    f"[FAILED] Dimension: {dimension_id} "
                    f"after {elapsed:.2f} sec"
                )

                print(f"[ERROR] {ex}")

                errors.append({
                    "dimension_id": dimension_id,
                    "error": str(ex)
                })

        print("\n" + "=" * 80)
        print("DIMENSION VALUE INDEX SUMMARY")
        print("=" * 80)

        print(f"Processed : {total}")
        print(f"Indexed   : {len(summary)}")
        print(f"Skipped   : {len(skipped)}")
        print(f"Failed    : {len(errors)}")

        if errors:
            print("\nErrors:")
            for err in errors:
                print(err)

        return {
            "connection_id": connection_id,
            "dimensions_processed": total,
            "indexed": len(summary),
            "skipped": len(skipped),
            "failed": len(errors),
            "results": summary,
            "skipped_results": skipped,
            "errors": errors
        }


    @staticmethod
    def delete_dimension_index(dimension_id: str):
        """
        Remove all indexed values for a semantic dimension.
        """

        query = text("""
            DELETE
            FROM dimension_value_index
            WHERE semantic_dimension_id = :dimension_id
        """)

        with engine.begin() as conn:

            result = conn.execute(
                query,
                {
                    "dimension_id": dimension_id
                }
            )

        return {
            "dimension_id": dimension_id,
            "deleted_values": result.rowcount
        }

    @staticmethod
    def _fetch_distinct_values(
        source_engine,
        table_name: str,
        column_name: str
    ):
        """
        Fetch distinct values from the source database.
        Supports multiple database engines.
        """

        dialect = source_engine.dialect.name

        if dialect == "mssql":

            table = f"[{table_name}]"
            column = f"[{column_name}]"

            query = text(f"""
                SELECT DISTINCT TOP ({DimensionValueIndexBuilder.MAX_INDEX_VALUES + 1}) {column}
                FROM {table}
                WHERE
                    {column} IS NOT NULL
                    AND LTRIM(RTRIM(CAST({column} AS NVARCHAR(MAX)))) <> ''
                    AND LEN(CAST({column} AS NVARCHAR(MAX))) <= 500
                ORDER BY {column}
            """)

        elif dialect == "postgresql":

            table = f'"{table_name}"'
            column = f'"{column_name}"'

            query = text(f"""
                SELECT DISTINCT {column}
                FROM {table}
                WHERE
                    {column} IS NOT NULL
                    AND BTRIM(CAST({column} AS TEXT)) <> ''
                    AND LENGTH(CAST({column} AS TEXT)) <= 500
                ORDER BY {column}
                LIMIT {DimensionValueIndexBuilder.MAX_INDEX_VALUES + 1}
            """)

        elif dialect == "mysql":

            table = f"`{table_name}`"
            column = f"`{column_name}`"

            query = text(f"""
                SELECT DISTINCT {column}
                FROM {table}
                WHERE
                    {column} IS NOT NULL
                    AND TRIM(CAST({column} AS CHAR)) <> ''
                    AND CHAR_LENGTH(CAST({column} AS CHAR)) <= 500
                ORDER BY {column}
                LIMIT {DimensionValueIndexBuilder.MAX_INDEX_VALUES + 1}
            """)

        else:
            raise NotImplementedError(
                f"Database dialect '{dialect}' is not supported."
            )

        with source_engine.connect() as conn:

            result = conn.execute(query)

            values = [
                row[0]
                for row in result.fetchall()
                if row[0] is not None
            ]


        return values


    @staticmethod
    def _normalize_value(value):
        """
        Normalize a business value for semantic matching.
        """

        if value is None:
            return None

        value = str(value)

        # Remove leading/trailing whitespace
        value = value.strip()

        # Convert to lowercase
        value = value.lower()

        # Collapse multiple spaces
        value = re.sub(r"\s+", " ", value)

        return value

    @staticmethod
    def _replace_dimension_values(
        connection_id: str,
        dimension_id: str,
        values: list
    ):
        """
        Replace all indexed values for a semantic dimension.
        """

        delete_query = text("""
            DELETE
            FROM dimension_value_index
            WHERE semantic_dimension_id = :dimension_id
        """)

        insert_query = text("""
            INSERT INTO dimension_value_index
            (
                connection_id,
                semantic_dimension_id,
                value,
                normalized_value
            )
            VALUES
            (
                :connection_id,
                :dimension_id,
                :value,
                :normalized_value
            )
        """)

        with engine.begin() as conn:

            # Remove existing index
            conn.execute(
                delete_query,
                {
                    "dimension_id": dimension_id
                }
            )

            # Nothing to insert
            if not values:
                return

            insert_data = [
                {
                    "connection_id": connection_id,
                    "dimension_id": dimension_id,
                    "value": value,
                    "normalized_value": DimensionValueIndexBuilder._normalize_value(value)
                }
                for value in values
            ]

            conn.execute(
                insert_query,
                insert_data
            )

    @staticmethod
    def _validate_dimension_mapping(
        source_engine,
        table_name: str,
        column_name: str
    ):
        """
        Validate that the mapped table and column
        exist in the source database.
        """

        query = text("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE
                TABLE_NAME = :table_name
                AND COLUMN_NAME = :column_name
        """)

        with source_engine.connect() as conn:

            row = conn.execute(
                query,
                {
                    "table_name": table_name,
                    "column_name": column_name
                }
            ).fetchone()

        if not row:
            raise ValueError(
                f"Invalid semantic mapping: "
                f"Table '{table_name}' "
                f"or column '{column_name}' "
                f"does not exist."
            )