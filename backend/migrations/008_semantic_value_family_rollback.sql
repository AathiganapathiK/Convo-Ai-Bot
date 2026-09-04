-- ===========================================================================
-- 008_semantic_value_family_rollback.sql
--
-- Reverses 008_semantic_value_family.sql.
--
-- Dropping the table removes every curated family. The resolver then stops
-- offering family values entirely and falls back to matching the stored
-- product-line values directly - the pre-008 behaviour, including the
-- confident-single-member problem 008 exists to prevent.
-- ===========================================================================

IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_value_family_lookup')
BEGIN
    DROP INDEX ix_value_family_lookup ON semantic_value_family;
END;
GO

IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_value_family')
BEGIN
    DROP TABLE semantic_value_family;
END;
GO
