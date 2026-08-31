-- ===========================================================================
-- 007_suggestion_proposal_rollback.sql
--
-- Undoes 007_suggestion_proposal.sql.
--
-- NOT run by tools/run_migrations.py. Apply deliberately:
--     python -m tools.run_rollback 007
--
-- WHAT IS LOST: generated proposals and their review status - what was accepted
-- and what was declined. Confirmed configuration is NOT affected: confirming
-- writes to semantic_table_config, semantic_dimensions and the rest, and those
-- rows stand on their own. Re-running the suggester regenerates proposals, at
-- the cost of another profiling pass and another round of model calls.
--
-- The evidence columns from migration 006 are left alone; only what 007 added
-- is removed.
-- ===========================================================================

IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_suggestion_pending')
BEGIN
    DROP INDEX ix_suggestion_pending ON semantic_suggestion_evidence;
END;
GO

IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_suggestion_handle')
BEGIN
    DROP INDEX ix_suggestion_handle ON semantic_suggestion_evidence;
END;
GO

IF EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'ck_suggestion_review_status')
BEGIN
    ALTER TABLE semantic_suggestion_evidence DROP CONSTRAINT ck_suggestion_review_status;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'review_note') IS NOT NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence DROP COLUMN review_note;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'reviewed_at') IS NOT NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence DROP COLUMN reviewed_at;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'reviewed_by') IS NOT NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence DROP COLUMN reviewed_by;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'review_status') IS NOT NULL
BEGIN
    IF EXISTS (SELECT * FROM sys.default_constraints WHERE name = 'df_suggestion_review_status')
        ALTER TABLE semantic_suggestion_evidence DROP CONSTRAINT df_suggestion_review_status;
    ALTER TABLE semantic_suggestion_evidence DROP COLUMN review_status;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'proposal_json') IS NOT NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence DROP COLUMN proposal_json;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'suggestion_id') IS NOT NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence DROP COLUMN suggestion_id;
END;
GO

IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '__schema_migrations')
BEGIN
    DELETE FROM __schema_migrations WHERE migration_name = '007_suggestion_proposal.sql';
END;
GO
