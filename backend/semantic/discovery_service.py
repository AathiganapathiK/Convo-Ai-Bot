from ai.insights import followup_generator
from ai.insights import followup_generator
import uuid, re
from sqlalchemy import text
from database import engine

class SemanticDiscoveryService:

    @staticmethod
    def discover(connection_id):
        if not connection_id:
            return []

        query = """
        SELECT
            st.table_name,
            sc.column_name,
            sc.data_type
        FROM schema_columns sc
        JOIN schema_tables st
            ON sc.table_id = st.table_id
        WHERE st.connection_id = :connection_id
        AND LOWER(st.table_name) NOT IN (
            'companies',
            'users',
            'roles',
            'permissions',
            'role_permissions',
            'user_roles',
            'chat_sessions',
            'chat_messages',
            'schema_tables',
            'schema_columns',
            'schema_relationships',
            'schema_drift_events',
            'database_connections',
            'audit_logs',
            'user_queries',
            'user_usage',
            'user_data_access',
            'role_column_access',
            'semantic_metrics',
            'semantic_dimensions',
            'api_keys',
            'base_config',
            'drifttest',
            'llm_fallbacks',
            'llm_models',
            'llm_providers',
            'provider_health'
        )
        """

        with engine.connect() as conn:
            rows = conn.execute(
                text(query),
                {"connection_id": connection_id}
            ).fetchall()

        # Track to prevent duplicates within this run
        seen_metrics = set()
        seen_dimensions = set()

        with engine.begin() as conn:
            # Delete existing discovered metrics/dimensions for this connection to prevent duplicates
            conn.execute(
                text("DELETE FROM semantic_metrics WHERE connection_id = :connection_id AND source='AUTO'"),
                {"connection_id": connection_id}
            )
            conn.execute(
                text("DELETE FROM semantic_dimensions WHERE connection_id = :connection_id AND source='AUTO'"),
                {"connection_id": connection_id}
            )

            for row in rows:
                # Access via index to support both SQLAlchemy 1.x and 2.x Row layouts
                table_name = row[0]
                column_name = row[1]
                data_type = row[2].lower()
                lower = column_name.lower()

                # Filter out technical and audit columns
                if SemanticDiscoveryService.is_technical_column(column_name):
                    continue
                # Generate metrics only for valid numeric business columns
                if SemanticDiscoveryService.is_metric_column(column_name, data_type):

                    metric_key = (
                        table_name.lower(),
                        lower
                    )

                    if metric_key not in seen_metrics:

                        seen_metrics.add(metric_key)

                        metric_id = str(uuid.uuid4())

                        metric_name = lower.replace(" ", "_")

                        business_name = (
                            SemanticDiscoveryService.generate_business_name(
                                table_name,
                                column_name
                            )
                        )

                        description = (
                            f"Semantic metric for {column_name} in {table_name}"
                        )

                        aggregation_type = (
                            SemanticDiscoveryService.detect_aggregation_type(
                                column_name
                            )
                        )

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
                                    source
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
                                    'AUTO'
                                )
                            """),
                            {
                                "metric_id": metric_id,
                                "connection_id": connection_id,
                                "metric_name": metric_name,
                                "business_name": business_name,
                                "description": description,
                                "table_name": table_name,
                                "column_name": column_name,
                                "aggregation_type": aggregation_type
                            }
                        )


                # Generate dimensions
                dimension_key = (table_name.lower(), lower)
                if SemanticDiscoveryService.is_dimension_column(
                     column_name,
                     data_type
                    ):

                    dimension_name = lower.replace(" ", "_")

                    # One semantic dimension per connection
                    dimension_key = dimension_name

                    print(
                        f"[DISCOVERY] table={table_name}, "
                        f"column={column_name}, "
                        f"dimension_name={dimension_name!r}, "
                        f"key={dimension_key!r}, "
                        f"already_seen={dimension_key in seen_dimensions}"
                    )
                    if dimension_key not in seen_dimensions:

                        seen_dimensions.add(dimension_key)

                        dimension_id = str(uuid.uuid4())

                        business_name = (
                            SemanticDiscoveryService.generate_business_name(
                                table_name,
                                column_name
                            )
                        )

                        description = (
                           f"Semantic dimension for {column_name} in {table_name}"
                        )

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
                                source
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
                                'AUTO'
                            )
                            """),
                            {
                                "dimension_id": dimension_id,
                                "connection_id": connection_id,
                                "dimension_name": dimension_name,
                                "business_name": business_name,
                                "description": description,
                                "table_name": table_name,
                                "column_name": column_name
                            }
                        )

        return rows

    @staticmethod
    def is_technical_column(
        column_name
    ):

        lower = column_name.lower()

        audit_columns = {

            "created_at",

            "updated_at",

            "created_by",

            "modified_by",

            "modifieddate",

            "rowguid"

        }

        if lower in audit_columns:
            return True

        technical_suffixes = [

            "id",

            "key",

            "fk",

            "pk"

        ]

        exceptions = {

            "valid",

            "grid",

            "hybrid",

            "liquid"

        }

        if lower in exceptions:
            return False

        return any(
            lower.endswith(suffix)
            for suffix in technical_suffixes
        )

    @staticmethod
    def detect_aggregation_type(
        column_name: str
    ):

        lower = column_name.lower()

        avg_columns = [
            "price",
            "cost",
            "margin",
            "rate",
            "discount",
            "percentage",
            "percent"
        ]

        count_columns = [
            "count",
            "number"
        ]

        sum_columns = [
            "sales",
            "revenue",
            "amount",
            "profit",
            "quantity",
            "total"
        ]

        if any(
            word in lower
            for word in avg_columns
        ):
            return "AVG"

        if any(
            word in lower
            for word in count_columns
        ):
            return "COUNT"

        if any(
            word in lower
            for word in sum_columns
        ):
            return "SUM"

        return None

    @staticmethod
    def generate_business_name(
        table_name: str,
        column_name: str
    ) -> str:
        """
        Converts:
        DimEmployee + SalesPersonFlag
        ->
        Sales Person Flag

        FactSales + SalesAmount
        ->
        Sales Amount
        """

        prefixes = [
            "Dim",
            "Fact",
            "Tbl",
            "VW",
            "View"
        ]

        cleaned_table = table_name

        for prefix in prefixes:

            if cleaned_table.startswith(prefix):
                cleaned_table = cleaned_table[len(prefix):]

        words = re.sub(
            r'(?<!^)(?=[A-Z])',
            ' ',
            column_name
        )

        return words.replace(
            "_",
            " "
        ).strip()


    @staticmethod
    def is_numeric_type(data_type: str):

        numeric_types = {

            "int",
            "bigint",
            "smallint",
            "tinyint",

            "decimal",
            "numeric",

            "money",
            "smallmoney",

            "float",
            "real"

        }

        return data_type.lower() in numeric_types


    @staticmethod
    def is_text_type(data_type: str):

        text_types = {

            "varchar",

            "nvarchar",

            "char",

            "nchar",

            "text",

            "ntext"

        }

        return data_type.lower() in text_types


    @staticmethod
    def is_date_type(data_type: str):

        date_types = {

            "date",

        "datetime",

        "datetime2",

        "smalldatetime",

        "datetimeoffset"

    }

        return data_type.lower() in date_types

    @staticmethod
    def is_guid_type(data_type: str):

        return data_type.lower() == "uniqueidentifier"

    @staticmethod
    def is_metric_column(
        column_name,
        data_type
    ):

        if not SemanticDiscoveryService.is_numeric_type(
            data_type
        ):
            return False

        lower = column_name.lower()

        rejected = {
            "id",
            "key",
            "flag",
            "code",
            "zipcode",
            "postalcode",
            "phone",
            "mobile"
        }

        if any(
            word in lower
            for word in rejected
        ):
            return False

        return True

    @staticmethod
    def is_dimension_column(
        column_name,
        data_type
    ):

        if SemanticDiscoveryService.is_guid_type(
            data_type
        ):
            return False

        if SemanticDiscoveryService.is_boolean_type(
            data_type
        ):
            return False

        if SemanticDiscoveryService.is_technical_column(
            column_name
        ):
            return False

        if (
            SemanticDiscoveryService.is_text_type(
                data_type
            )
            or
            SemanticDiscoveryService.is_date_type(
                data_type
            )
        ):
            return True

        return False

    @staticmethod
    def is_boolean_type(data_type: str):

        return data_type.lower() == "bit"


    # METRIC_KEYWORDS = [
    #     "sales",
    #     "revenue",
    #     "amount",
    #     "cost",
    #     "price",
    #     "profit",
    #     "quantity",
    #     "target"
    # ]

    # DIMENSION_KEYWORDS = [
    #     "name",
    #     "region",
    #     "date",
    #     "category",
    #     "product",
    #     "customer",
    #     "employee"
    # ]

    # BAD_METRICS = [
    #     "salesordernumber",
    #     "salesperson",
    #     "targetmonth"
    # ]

    # BAD_DIMENSIONS = [
    #     "productkey",
    #     "orderdate",
    #     "rowguid",
    #     "modifieddate"
    # ]