-- ============================================================================
-- Enterprise Security Framework — Database Migration 002
-- Database: adv_works (SQL Server)
-- Purpose: Change audit columns datatype in semantic tables to match the 
--          employee_id identifier (VARCHAR(50)) used throughout the system.
-- ============================================================================

PRINT '=== Starting Migration 002: Semantic Audit Types ===';

-- 1. Alter semantic_metrics audit columns
IF EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'semantic_metrics' 
      AND COLUMN_NAME = 'created_by' 
      AND DATA_TYPE = 'uniqueidentifier'
)
BEGIN
    PRINT 'Altering semantic_metrics.created_by to VARCHAR(50)';
    ALTER TABLE semantic_metrics ALTER COLUMN created_by VARCHAR(50) NULL;
END;
GO

IF EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'semantic_metrics' 
      AND COLUMN_NAME = 'updated_by' 
      AND DATA_TYPE = 'uniqueidentifier'
)
BEGIN
    PRINT 'Altering semantic_metrics.updated_by to VARCHAR(50)';
    ALTER TABLE semantic_metrics ALTER COLUMN updated_by VARCHAR(50) NULL;
END;
GO


-- 2. Alter semantic_dimensions audit columns
IF EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'semantic_dimensions' 
      AND COLUMN_NAME = 'created_by' 
      AND DATA_TYPE = 'uniqueidentifier'
)
BEGIN
    PRINT 'Altering semantic_dimensions.created_by to VARCHAR(50)';
    ALTER TABLE semantic_dimensions ALTER COLUMN created_by VARCHAR(50) NULL;
END;
GO

IF EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_NAME = 'semantic_dimensions' 
      AND COLUMN_NAME = 'updated_by' 
      AND DATA_TYPE = 'uniqueidentifier'
)
BEGIN
    PRINT 'Altering semantic_dimensions.updated_by to VARCHAR(50)';
    ALTER TABLE semantic_dimensions ALTER COLUMN updated_by VARCHAR(50) NULL;
END;
GO

PRINT '=== Migration 002: Semantic Audit Types Complete ===';
GO
