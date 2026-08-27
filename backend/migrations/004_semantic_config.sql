-- ===========================================================================
-- 004_semantic_config.sql
--
-- Gate 2 - admin-configurable semantic layer.
--
-- Purpose: move business meaning out of application code and into data, so a
-- new table becomes answerable through configuration rather than a code change.
-- Replaces the hardcoded SNAPSHOT_SALES_BINDINGS dictionary in
-- semantic/semantic_plan_builder.py.
--
-- Additive only. No table is dropped, no column is renamed, and every new
-- column is nullable or defaulted, so existing rows stay valid and the running
-- application keeps working whether or not the new code is deployed yet.
--
-- Rollback: 004_semantic_config_rollback.sql
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. semantic_domains - business areas ("Sales", "Order Pending", "Receivables")
--
-- Fixes the recorded bug where "show order pendings" resolved against the Sales
-- table because nothing bound a business area to its tables.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_domains')
BEGIN
    CREATE TABLE semantic_domains
    (
        domain_id       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        connection_id   UNIQUEIDENTIFIER NOT NULL
                        REFERENCES database_connections(connection_id),

        domain_name     NVARCHAR(128) NOT NULL,
        business_name   NVARCHAR(128) NOT NULL,

        -- Comma-separated business synonyms, matching the convention already
        -- used by semantic_metrics.synonyms and semantic_dimensions.synonyms.
        synonyms        NVARCHAR(MAX) NULL,
        description     NVARCHAR(MAX) NULL,

        is_active       BIT NOT NULL DEFAULT 1,

        created_at      DATETIME2 DEFAULT GETDATE(),
        updated_at      DATETIME2 DEFAULT GETDATE(),
        created_by      VARCHAR(50) NULL,
        updated_by      VARCHAR(50) NULL,

        CONSTRAINT uq_semantic_domain UNIQUE (connection_id, domain_name)
    );
END;
GO


-- ---------------------------------------------------------------------------
-- 2. semantic_table_config - one row per physical table
--
-- Holds the domain binding and the table's time behaviour. This is what fills
-- TimeResolver._discover_capability(), which currently returns an empty
-- TimeCapability() and is the reason temporal handling is hardcoded.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_table_config')
BEGIN
    CREATE TABLE semantic_table_config
    (
        config_id               UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        connection_id           UNIQUEIDENTIFIER NOT NULL
                                REFERENCES database_connections(connection_id),

        table_name              NVARCHAR(128) NOT NULL,

        -- Which business area this table serves. Nullable so a table can exist
        -- unassigned; unassigned must fail loudly at query time, never default.
        domain_id               UNIQUEIDENTIFIER NULL
                                REFERENCES semantic_domains(domain_id),

        -- SNAPSHOT    - period lives in separate columns (CY, PY, PYTD, ...)
        -- DATE_COLUMN - period is filtered from a real date column
        -- NONE        - table carries no time dimension
        temporal_strategy       NVARCHAR(30) NULL,

        -- Used when temporal_strategy = DATE_COLUMN.
        date_column             NVARCHAR(128) NULL,

        -- Month label shown to the user, e.g. InvMonth ("A April").
        month_column            NVARCHAR(128) NULL,

        -- Column to ORDER BY for month sequence. NOT necessarily the same as
        -- month_column: on the sales table InvMonth's prefix letter encodes
        -- fiscal order (A April ... L March) and sorts correctly as text, while
        -- DocMonth is a calendar number and would place January first, which is
        -- wrong for an April-March fiscal year.
        month_sort_column       NVARCHAR(128) NULL,

        -- 1 = January (default, calendar year). 4 = April for a fiscal year
        -- running April to March. Never inferred from data.
        fiscal_year_start_month INT NOT NULL DEFAULT 1,

        -- 0 = system suggestion awaiting review, 1 = a human approved it.
        -- Nothing unconfirmed may be treated as authoritative.
        is_confirmed            BIT NOT NULL DEFAULT 0,

        created_at              DATETIME2 DEFAULT GETDATE(),
        updated_at              DATETIME2 DEFAULT GETDATE(),
        created_by              VARCHAR(50) NULL,
        updated_by              VARCHAR(50) NULL,

        CONSTRAINT uq_semantic_table_config UNIQUE (connection_id, table_name),

        CONSTRAINT ck_temporal_strategy
            CHECK (temporal_strategy IS NULL
                   OR temporal_strategy IN ('SNAPSHOT', 'DATE_COLUMN', 'NONE')),

        CONSTRAINT ck_fiscal_year_start_month
            CHECK (fiscal_year_start_month BETWEEN 1 AND 12)
    );
END;
GO


-- ---------------------------------------------------------------------------
-- 3. semantic_snapshot_mapping - which column holds which period
--
-- Replaces the hardcoded SNAPSHOT_SALES_BINDINGS dictionary.
--
-- period_scope is the important one and exists because of a verified trap in
-- the live data: CY holds the current fiscal year TO DATE (five months at the
-- time of writing) while PY holds the previous fiscal year IN FULL (twelve
-- months). Comparing them directly reports a 63% collapse where the true
-- like-for-like figure, CY against PYTD, is 14.5% growth. A year-on-year
-- comparison of a partial current year must resolve to the TO_DATE row.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_snapshot_mapping')
BEGIN
    CREATE TABLE semantic_snapshot_mapping
    (
        mapping_id      UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        connection_id   UNIQUEIDENTIFIER NOT NULL
                        REFERENCES database_connections(connection_id),

        table_name      NVARCHAR(128) NOT NULL,

        -- 0 = current period, 1 = previous, 2 = two back, and so on.
        period_offset   INT NOT NULL,

        -- VALUE    - a monetary or amount measure (CY, PY, PYTD)
        -- QUANTITY - a unit/volume measure (CYQ, PYQ)
        measure_kind    NVARCHAR(20) NOT NULL DEFAULT 'VALUE',

        -- FULL    - the complete period
        -- TO_DATE - the period truncated to the same point as the current one
        period_scope    NVARCHAR(20) NOT NULL DEFAULT 'FULL',

        -- The physical column, e.g. CY, PY, PYTD, CYQ.
        column_name     NVARCHAR(128) NOT NULL,

        is_confirmed    BIT NOT NULL DEFAULT 0,

        created_at      DATETIME2 DEFAULT GETDATE(),
        updated_at      DATETIME2 DEFAULT GETDATE(),
        created_by      VARCHAR(50) NULL,
        updated_by      VARCHAR(50) NULL,

        CONSTRAINT uq_semantic_snapshot_mapping
            UNIQUE (connection_id, table_name, period_offset, measure_kind, period_scope),

        CONSTRAINT ck_measure_kind
            CHECK (measure_kind IN ('VALUE', 'QUANTITY')),

        CONSTRAINT ck_period_scope
            CHECK (period_scope IN ('FULL', 'TO_DATE')),

        CONSTRAINT ck_period_offset
            CHECK (period_offset >= 0)
    );
END;
GO


-- ---------------------------------------------------------------------------
-- 4. semantic_dimensions - dimension roles and the exclusion switch
--
-- dimension_role stops a load timestamp becoming a grouping dimension.
-- is_excluded switches off duplicate or unusable columns outright: the
-- State1/State2/State3/StateCode family that all hold the same values and
-- caused the "UT - state1/statev1" failure, MktType1, and createddate.
-- ---------------------------------------------------------------------------
IF COL_LENGTH('semantic_dimensions', 'dimension_role') IS NULL
BEGIN
    ALTER TABLE semantic_dimensions ADD dimension_role NVARCHAR(30) NULL;
END;
GO

IF COL_LENGTH('semantic_dimensions', 'is_excluded') IS NULL
BEGIN
    ALTER TABLE semantic_dimensions ADD is_excluded BIT NOT NULL
        CONSTRAINT df_semantic_dimensions_is_excluded DEFAULT 0;
END;
GO

IF COL_LENGTH('semantic_dimensions', 'is_confirmed') IS NULL
BEGIN
    ALTER TABLE semantic_dimensions ADD is_confirmed BIT NOT NULL
        CONSTRAINT df_semantic_dimensions_is_confirmed DEFAULT 0;
END;
GO


-- ---------------------------------------------------------------------------
-- 5. semantic_metrics - the exclusion switch
--
-- Lets InvMonth, DocMonth, Sno, OrderNo and Docnum be switched off as measures.
-- They are numeric identifiers that auto-discovery registered as metrics
-- because is_metric_column() tests only "numeric and the name avoids
-- id/key/flag/code".
-- ---------------------------------------------------------------------------
IF COL_LENGTH('semantic_metrics', 'is_excluded') IS NULL
BEGIN
    ALTER TABLE semantic_metrics ADD is_excluded BIT NOT NULL
        CONSTRAINT df_semantic_metrics_is_excluded DEFAULT 0;
END;
GO

IF COL_LENGTH('semantic_metrics', 'is_confirmed') IS NULL
BEGIN
    ALTER TABLE semantic_metrics ADD is_confirmed BIT NOT NULL
        CONSTRAINT df_semantic_metrics_is_confirmed DEFAULT 0;
END;
GO


-- ---------------------------------------------------------------------------
-- 6. Indexes for the query-time lookups
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_table_config_lookup')
BEGIN
    CREATE INDEX ix_table_config_lookup
        ON semantic_table_config (connection_id, table_name);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_snapshot_mapping_lookup')
BEGIN
    CREATE INDEX ix_snapshot_mapping_lookup
        ON semantic_snapshot_mapping (connection_id, table_name, period_offset);
END;
GO
