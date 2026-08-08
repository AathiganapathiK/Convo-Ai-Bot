from semantic import dimension_value_index_builder
from security import row_security
import uuid, re
from sqlalchemy import text
from database import engine
from semantic.dimension_value_index_builder import DimensionValueIndexBuilder


class SemanticDiscoveryService:

    EXCLUDED_DIMENSION_TYPES = {
        "text",
        "ntext",
        "xml",
        "image",
        "binary",
        "varbinary",
        "sql_variant"
    }

    EXCLUDED_DIMENSION_PATTERNS = {
        "definition",
        "script",
        "sql",
        "ddl",
        "procedure",
        "function",
        "view_definition"
    }

    EXCLUDED_DIMENSION_COLUMNS = {
        # Authentication    
        "password",
        "passwd",
        "pwd",
        "username",
        "user_name",
        "login",
        "email",
        "phone",
        "mobile",

        # Security
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "apikey",
        "jwt",
        "hash",
        "salt",

        # System identifiers
        "guid",
        "uuid",
        "sessionid",
        "session_id",

        # Audit
        "createdby",
        "modifiedby",
        "created_by",
        "modified_by"
    }
    EXCLUDED_TABLE_PATTERNS = {
        "backup",
        "_backup",
        "copy_",
        "_copy",
        "temp",
        "_temp",
        "tmp",
        "_tmp",
        "archive",
        "_archive",
        "history",
        "_history",
        "test",
        "_test"
    }

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
            # conn.execute(
            #     text("DELETE FROM semantic_metrics WHERE connection_id = :connection_id AND source='AUTO'"),
            #     {"connection_id": connection_id}
            # )
            # conn.execute(
            #     text("DELETE FROM semantic_dimensions WHERE connection_id = :connection_id AND source='AUTO'"),
            #     {"connection_id": connection_id}
            # )
            discovered_metrics = set()
            discovered_dimensions = set()

            for row in rows:
                # Access via index to support both SQLAlchemy 1.x and 2.x Row layouts
                table_name = row[0]
                column_name = row[1]
                data_type = row[2].lower()
                lower = column_name.lower()
                if not SemanticDiscoveryService.should_discover_table(table_name):
                    continue

                # Filter out technical and audit columns
                if SemanticDiscoveryService.is_technical_column(column_name):
                    continue
                # Generate metrics only for valid numeric business columns
                if SemanticDiscoveryService.is_metric_column(column_name, data_type):

                    metric_key = (
                        table_name.lower(),
                        lower
                    )
                    discovered_metrics.add((table_name.lower(), column_name.lower()))

                    if metric_key not in seen_metrics:

                        seen_metrics.add(metric_key)

                        metric_id = str(uuid.uuid4())

                        metric_name = lower.replace(" ", "_")

                        business_name = SemanticDiscoveryService.generate_business_name(
                            table_name,
                            column_name
                        )

                        description = (
                            f"Semantic metric for {column_name} in {table_name}"
                        )

                        aggregation_type = SemanticDiscoveryService.detect_aggregation_type(
                            column_name
                        )

                        existing_metric = conn.execute(
                            text("""
                                SELECT metric_id
                                FROM semantic_metrics
                                WHERE connection_id = :connection_id
                                  AND LOWER(table_name) = LOWER(:table_name)
                                  AND LOWER(column_name) = LOWER(:column_name)
                            """),
                            {
                                "connection_id": connection_id,
                                "table_name": table_name,
                                "column_name": column_name
                            }
                        ).fetchone()

                        if existing_metric:

                            conn.execute(
                                text("""
                                    UPDATE semantic_metrics
                                    SET
                                        aggregation_type = :aggregation_type,
                                        source = 'AUTO',
                                        table_name = :table_name,
                                        column_name = :column_name
                                    WHERE metric_id = :metric_id
                                """),
                                {
                                    "aggregation_type": aggregation_type,
                                    "table_name": table_name,
                                    "column_name": column_name,
                                    "metric_id": existing_metric.metric_id
                                }
                            )

                        else:

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
                if SemanticDiscoveryService.is_dimension_column(column_name, data_type):
                    is_date = SemanticDiscoveryService.is_date_type(data_type)
                    variants = []
                    
                    if is_date:
                        base_bus_name = SemanticDiscoveryService.generate_business_name(table_name, column_name)
                        
                        # Date
                        date_bus_name = base_bus_name if "date" in base_bus_name.lower() else f"{base_bus_name} Date"
                        variants.append({
                            "suffix": "date",
                            "business_name": date_bus_name,
                            "synonyms": "date,dt,day",
                            "semantic_category": "TIME_DATE"
                        })
                        # Year
                        variants.append({
                            "suffix": "year",
                            "business_name": f"{base_bus_name} Year",
                            "synonyms": "year,yr,calendar year",
                            "semantic_category": "TIME_YEAR"
                        })
                        # Quarter
                        variants.append({
                            "suffix": "quarter",
                            "business_name": f"{base_bus_name} Quarter",
                            "synonyms": "quarter,qtr",
                            "semantic_category": "TIME_QUARTER"
                        })
                        # Month
                        variants.append({
                            "suffix": "month",
                            "business_name": f"{base_bus_name} Month",
                            "synonyms": "month,mth,calendar month",
                            "semantic_category": "TIME_MONTH"
                        })
                        # Week
                        variants.append({
                            "suffix": "week",
                            "business_name": f"{base_bus_name} Week",
                            "synonyms": "week,wk",
                            "semantic_category": "TIME_WEEK"
                        })
                        # Day
                        variants.append({
                            "suffix": "day",
                            "business_name": f"{base_bus_name} Day",
                            "synonyms": "day,dy,day of month",
                            "semantic_category": "TIME_DAY"
                        })
                    else:
                        dimension_name = lower.replace(" ", "_")
                        business_name = SemanticDiscoveryService.generate_business_name(table_name, column_name)
                        semantic_category = SemanticDiscoveryService.detect_semantic_category(table_name, column_name, data_type)
                        sql_expression = f"{table_name}.{column_name}"

                        variants.append({
                            "suffix": None,
                            "business_name": business_name,
                            "synonyms": None,
                            "semantic_category": semantic_category,
                            "sql_expression": sql_expression
                        })

                    for var in variants:
                        suffix = var["suffix"]
                        v_dim_name = f"{lower.replace(' ', '_')}_{suffix}" if suffix else lower.replace(" ", "_")
                        dimension_key = (table_name.lower(), v_dim_name)
                        
                        discovered_dimensions.add((table_name.lower(), column_name.lower()))

                        print(
                            f"[DISCOVERY] table={table_name}, "
                            f"column={column_name}, "
                            f"dimension_name={v_dim_name!r}, "
                            f"key={dimension_key!r}, "
                            f"already_seen={dimension_key in seen_dimensions}"
                        )
                        if dimension_key not in seen_dimensions:
                            seen_dimensions.add(dimension_key)
                            dimension_id = str(uuid.uuid4())
                            
                            business_name = var["business_name"]
                            semantic_category = var["semantic_category"]
                            synonyms = var["synonyms"]
                            
                            description = f"Semantic dimension for {column_name} ({suffix if suffix else 'standard'}) in {table_name}"
                            
                            existing_dimension = conn.execute(
                                text("""
                                    SELECT dimension_id, synonyms, semantic_category
                                    FROM semantic_dimensions
                                    WHERE connection_id = :connection_id
                                      AND LOWER(table_name) = LOWER(:table_name)
                                      AND LOWER(column_name) = LOWER(:column_name)
                                      AND LOWER(dimension_name) = LOWER(:dimension_name)
                                """),
                                {
                                    "connection_id": connection_id,
                                    "table_name": table_name,
                                    "column_name": column_name,
                                    "dimension_name": v_dim_name
                                }
                            ).fetchone()

                            if existing_dimension:
                                # Preserve manually added/existing synonyms if they are already populated
                                updated_synonyms = existing_dimension.synonyms if (existing_dimension.synonyms is not None and existing_dimension.synonyms != "") else synonyms
                                # Preserve semantic category if it was customized (not UNKNOWN/None)
                                updated_category = existing_dimension.semantic_category if (existing_dimension.semantic_category is not None and existing_dimension.semantic_category != "UNKNOWN") else semantic_category

                                conn.execute(
                                    text("""
                                        UPDATE semantic_dimensions
                                        SET
                                            semantic_category = :semantic_category,
                                            synonyms = :synonyms,
                                            source = 'AUTO',
                                            table_name = :table_name,
                                            column_name = :column_name
                                        WHERE dimension_id = :dimension_id
                                    """),
                                    {
                                        "semantic_category": updated_category,
                                        "synonyms": updated_synonyms,
                                        "table_name": table_name,
                                        "column_name": column_name,
                                        "dimension_id": existing_dimension.dimension_id
                                    }
                                )
                            else:
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
                                            semantic_category,
                                            source,
                                            synonyms
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
                                            :semantic_category,
                                            'AUTO',
                                            :synonyms
                                        )
                                    """),
                                    {
                                        "dimension_id": dimension_id,
                                        "connection_id": connection_id,
                                        "dimension_name": v_dim_name,
                                        "business_name": business_name,
                                        "description": description,
                                        "table_name": table_name,
                                        "column_name": column_name,
                                        "semantic_category": semantic_category,
                                        "synonyms": synonyms
                                    }
                                )
                            
            existing_metrics = conn.execute(
                text("""
                    SELECT metric_id, table_name, column_name
                    FROM semantic_metrics
                    WHERE connection_id = :connection_id
                    AND source = 'AUTO'
                """),
                {"connection_id": connection_id}
            ).fetchall()

            for metric in existing_metrics:
                m_table = metric.table_name.lower() if metric.table_name else ""
                m_column = metric.column_name.lower() if metric.column_name else ""
                if (m_table, m_column) not in discovered_metrics:
                    conn.execute(
                        text("""
                            DELETE FROM semantic_metrics
                            WHERE metric_id = :metric_id
                        """),
                        {"metric_id": metric.metric_id}
                    )

            existing_dimensions = conn.execute(
                text("""
                    SELECT dimension_id, table_name, column_name
                    FROM semantic_dimensions
                    WHERE connection_id = :connection_id
                    AND source = 'AUTO'
                """),
                {"connection_id": connection_id}
            ).fetchall()

            for dimension in existing_dimensions:
                d_table = dimension.table_name.lower() if dimension.table_name else ""
                d_column = dimension.column_name.lower() if dimension.column_name else ""
                if (d_table, d_column) not in discovered_dimensions:

                    # Delete indexed values first (child records)
                    conn.execute(
                        text("""
                            DELETE FROM dimension_value_index
                            WHERE semantic_dimension_id = :dimension_id
                        """),
                        {"dimension_id": dimension.dimension_id}
                    )

                    # Then delete the semantic dimension (parent record)
                    conn.execute(
                        text("""
                            DELETE FROM semantic_dimensions
                            WHERE dimension_id = :dimension_id
                        """),
                        {"dimension_id": dimension.dimension_id}
                    )

            print(f"Discovered {len(discovered_metrics)} metrics")
            print(f"Discovered {len(discovered_dimensions)} dimensions")
        
        print("\n========== STARTING DIMENSION VALUE INDEX ==========")

        result = DimensionValueIndexBuilder.build_all(connection_id)

        print(f"Indexed: {result['dimensions_processed']}")
        print(f"Failed : {result['failed']}")

        for error in result["errors"]:
            print(error)

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
            "datetimeoffset",
            "timestamp"
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

        if not SemanticDiscoveryService.should_index_as_dimension(
            column_name,
            data_type
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

    @staticmethod
    def should_index_as_dimension(
        column_name: str,
        data_type: str
    ):
        """
        Determine whether a column is suitable for
        semantic dimension indexing.
        """

        data_type = data_type.lower()

        if (
            data_type
            in SemanticDiscoveryService.EXCLUDED_DIMENSION_TYPES
        ):
            return False

        lower = column_name.lower()

        # Exact column exclusions
        if lower in SemanticDiscoveryService.EXCLUDED_DIMENSION_COLUMNS:
            return False

        # Pattern exclusions
        for pattern in SemanticDiscoveryService.EXCLUDED_DIMENSION_PATTERNS:
            if pattern in lower:
                return False

        return True


    @staticmethod
    def build_dimension_value_index(connection_id):
        """
        Build the searchable index of all dimension values for a datasource.
        """

        print("\n========== DIMENSION VALUE INDEX BUILD ==========")
        print("Clearing previous value index...")

        try: 
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        DELETE
                        FROM dimension_value_index
                        WHERE connection_id = :connection_id
                    """),
                    {
                        "connection_id": connection_id
                    }
                )

            with engine.connect() as conn:

                dimensions = conn.execute(
                    text("""
                        SELECT
                            dimension_id,
                            table_name,
                            column_name
                        FROM semantic_dimensions
                        WHERE connection_id = :connection_id
                        AND is_active = 1
                    """),
                    {
                        "connection_id": connection_id
                    }
                ).fetchall()
        except Exception:
            import traceback
            traceback.print_exc()
            raise

        print(f"Dimensions Found : {len(dimensions)}")


    @staticmethod
    def should_discover_table(table_name: str):
        """
        Determine whether a table should participate
        in semantic discovery.
        """

        lower = table_name.lower()

        for pattern in SemanticDiscoveryService.EXCLUDED_TABLE_PATTERNS:
            if pattern in lower:
                return False

        return True

    @staticmethod
    def detect_semantic_category(
        table_name: str,
        column_name: str,
        data_type: str
    ) -> str:
        """
        Detect semantic category based on table name, column name, and data type.
        """
        SEMANTIC_PATTERNS = {
            "Geography": {
                "region", "country", "state", "city", "territory", "postal", "address", "location"
            },
            "Time": {
                "date", "time", "month", "year", "quarter", "day", "week", "calendar", "period"
            },
            "Organization": {
                "company", "department", "division", "organization", "org", "store", "branch"
            },
            "Product": {
                "product", "item", "sku", "category", "subcategory", "model", "brand", "color", "size"
            },
            "Finance": {
                "sales", "revenue", "cost", "price", "amount", "profit", "tax", "margin", "budget", "finance"
            },
            "Document": {
                "order", "invoice", "document", "receipt", "contract", "number", "code"
            },
            "Customer": {
                "customer", "client", "buyer", "subscriber"
            },
            "Human Resources": {
                "employee", "salesperson", "manager", "staff", "user", "role", "salary", "hire"
            },
            "Identifier": {
                "id", "key", "code", "guid", "uuid"
            }
        }

        table_lower = table_name.lower()
        column_lower = column_name.lower()

        # Tokenize camelCase, snake_case, and other non-alphanumeric formats
        table_tokens = set()
        if table_name:
            t_toks = re.findall(r'[a-zA-Z0-9]+', table_name)
            for t in t_toks:
                parts = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)', t)
                table_tokens.update(p.lower() for p in parts)

        column_tokens = set()
        if column_name:
            c_toks = re.findall(r'[a-zA-Z0-9]+', column_name)
            for c in c_toks:
                parts = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z][a-z0-9]|\b)', c)
                column_tokens.update(p.lower() for p in parts)

        all_tokens = table_tokens.union(column_tokens)

        for category, patterns in SEMANTIC_PATTERNS.items():
            for pattern in patterns:
                # Require exact match for short keywords to prevent false positives
                if len(pattern) <= 3:
                    if pattern in all_tokens:
                        return category
                else:
                    if any(pattern in token for token in all_tokens):
                        return category

        return "Other"

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



