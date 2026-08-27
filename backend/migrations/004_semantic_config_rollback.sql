-- ===========================================================================
-- 004_semantic_config_rollback.sql
--
-- Undoes 004_semantic_config.sql, returning the schema to its state before
-- Gate 2 configuration was introduced.
--
-- NOT run by tools/run_migrations.py. Apply deliberately and by hand:
--     python tools/run_rollback.py 004
-- or execute this file directly in SSMS against the target database.
--
-- WHAT IS LOST: only configuration - domain definitions, temporal strategies,
-- snapshot mappings, dimension roles and exclusion flags. No business data is
-- touched, because 004 created nothing that holds business data. Re-running the
-- forward migration afterwards gives a clean, empty configuration to re-enter.
--
-- Order matters: the child table referencing semantic_domains is dropped first,
-- otherwise the foreign key blocks it.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. Indexes (dropped with their tables, but explicit for clarity when a
--    partial application left a table behind)
-- ---------------------------------------------------------------------------
IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_snapshot_mapping_lookup')
BEGIN
    DROP INDEX ix_snapshot_mapping_lookup ON semantic_snapshot_mapping;
END;
GO

IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_table_config_lookup')
BEGIN
    DROP INDEX ix_table_config_lookup ON semantic_table_config;
END;
GO


-- ---------------------------------------------------------------------------
-- 2. Added columns on semantic_metrics
--    The DEFAULT constraint must go before the column it defaults.
-- ---------------------------------------------------------------------------
IF COL_LENGTH('semantic_metrics', 'is_confirmed') IS NOT NULL
BEGIN
    IF EXISTS (SELECT * FROM sys.default_constraints WHERE name = 'df_semantic_metrics_is_confirmed')
        ALTER TABLE semantic_metrics DROP CONSTRAINT df_semantic_metrics_is_confirmed;
    ALTER TABLE semantic_metrics DROP COLUMN is_confirmed;
END;
GO

IF COL_LENGTH('semantic_metrics', 'is_excluded') IS NOT NULL
BEGIN
    IF EXISTS (SELECT * FROM sys.default_constraints WHERE name = 'df_semantic_metrics_is_excluded')
        ALTER TABLE semantic_metrics DROP CONSTRAINT df_semantic_metrics_is_excluded;
    ALTER TABLE semantic_metrics DROP COLUMN is_excluded;
END;
GO


-- ---------------------------------------------------------------------------
-- 3. Added columns on semantic_dimensions
--
--    NOTE: semantic_category is deliberately NOT dropped. It pre-dates this
--    migration - it already existed on the live table before Gate 2 - and
--    removing it would break the resolver and the plan builder, which read it.
-- ---------------------------------------------------------------------------
IF COL_LENGTH('semantic_dimensions', 'is_confirmed') IS NOT NULL
BEGIN
    IF EXISTS (SELECT * FROM sys.default_constraints WHERE name = 'df_semantic_dimensions_is_confirmed')
        ALTER TABLE semantic_dimensions DROP CONSTRAINT df_semantic_dimensions_is_confirmed;
    ALTER TABLE semantic_dimensions DROP COLUMN is_confirmed;
END;
GO

IF COL_LENGTH('semantic_dimensions', 'is_excluded') IS NOT NULL
BEGIN
    IF EXISTS (SELECT * FROM sys.default_constraints WHERE name = 'df_semantic_dimensions_is_excluded')
        ALTER TABLE semantic_dimensions DROP CONSTRAINT df_semantic_dimensions_is_excluded;
    ALTER TABLE semantic_dimensions DROP COLUMN is_excluded;
END;
GO

IF COL_LENGTH('semantic_dimensions', 'dimension_role') IS NOT NULL
BEGIN
    ALTER TABLE semantic_dimensions DROP COLUMN dimension_role;
END;
GO


-- ---------------------------------------------------------------------------
-- 4. New tables, children before parents
-- ---------------------------------------------------------------------------
IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_snapshot_mapping')
BEGIN
    DROP TABLE semantic_snapshot_mapping;
END;
GO

IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_table_config')
BEGIN
    DROP TABLE semantic_table_config;
END;
GO

IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_domains')
BEGIN
    DROP TABLE semantic_domains;
END;
GO


-- ---------------------------------------------------------------------------
-- 5. Forget the migration so the forward script can run again cleanly
-- ---------------------------------------------------------------------------
IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '__schema_migrations')
BEGIN
    DELETE FROM __schema_migrations WHERE migration_name = '004_semantic_config.sql';
END;
GO
