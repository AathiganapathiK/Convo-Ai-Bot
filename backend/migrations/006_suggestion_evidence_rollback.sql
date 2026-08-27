-- ===========================================================================
-- 006_suggestion_evidence_rollback.sql
--
-- Undoes 006_suggestion_evidence.sql.
--
-- NOT run by tools/run_migrations.py. Apply deliberately:
--     python -m tools.run_rollback 006
--
-- WHAT IS LOST: the recorded profile and reasoning behind pending suggestions.
-- No business data and no confirmed configuration is affected - the config
-- tables from migration 004 are untouched. Re-running the suggestion service
-- regenerates evidence from scratch, at the cost of re-profiling and re-calling
-- the model.
-- ===========================================================================

IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_suggestion_evidence_lookup')
BEGIN
    DROP INDEX ix_suggestion_evidence_lookup ON semantic_suggestion_evidence;
END;
GO

IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_suggestion_evidence')
BEGIN
    DROP TABLE semantic_suggestion_evidence;
END;
GO

IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '__schema_migrations')
BEGIN
    DELETE FROM __schema_migrations WHERE migration_name = '006_suggestion_evidence.sql';
END;
GO
