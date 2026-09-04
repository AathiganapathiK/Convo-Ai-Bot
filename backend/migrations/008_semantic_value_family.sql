-- ===========================================================================
-- 008_semantic_value_family.sql
--
-- Gate 3 - curated value families for a dimension.
--
-- THE PROBLEM
--
-- Some dimensions store a composite key rather than the business entity a
-- user names. PBI_ENES_ORDER_PENDING_SUMMARY.Brand is the live example: it is
-- named Brand, confirmed, and its 43 values are brand x product-line pairs -
-- RAMRAJ DHOTI, RAMRAJ PANT, VIVEAGHAM DHOTI, UATHAYAM SHIRT. The brand a
-- customer actually names - "Ramraj" - is not a stored value anywhere.
--
-- Asked for "Ramraj brand" the resolver had nothing exact to match, fell
-- through to fuzzy matching, and returned RAMRAJ LITTLESTARS - one arbitrary
-- product line out of twelve - as a confident SINGLE_MATCH. A kidswear figure
-- was presented as the whole brand.
--
-- WHY THIS IS A TABLE AND NOT A PREFIX RULE
--
-- A string rule over the stored values cannot be trusted on this data:
--
--   * VIVEAGA (11 values) and VIVEAGHAM (9 values) coexist on ProdGrp1 and
--     may or may not be one brand. Only a human can say.
--   * RAMYYAM SAREE sits beside RAMRAJ *. A shared stem is exactly how a
--     silent wrong answer gets built.
--   * BAHAMA, GENISTAA, KOKHILA and UNIBRO are bare brands with no product
--     suffix, so "the first token before the space" is not a uniform rule.
--
-- Membership is therefore recorded explicitly, one row per member, reviewed by
-- a person, and never inferred at runtime.
--
-- GENERALITY
--
-- Nothing here is specific to brands or to RAMRAJ. A family is any curated
-- grouping of stored values under a name a user would say, on any dimension.
--
-- Additive only. No table is dropped and no column is renamed.
--
-- Rollback: 008_semantic_value_family_rollback.sql
-- ===========================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_value_family')
BEGIN
    CREATE TABLE semantic_value_family
    (
        family_row_id   UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        connection_id   UNIQUEIDENTIFIER NOT NULL
                        REFERENCES database_connections(connection_id),

        -- The dimension the family lives on. A family is scoped to one
        -- dimension: the same name may group different members on a different
        -- column, and the resolver must never carry membership across.
        dimension_id    UNIQUEIDENTIFIER NOT NULL
                        REFERENCES semantic_dimensions(dimension_id),

        -- What the user says. "RAMRAJ". This is matched against the question
        -- as though it were a stored value, so it must be the business name
        -- and not a description.
        family_name     NVARCHAR(128) NOT NULL,

        -- One stored value belonging to the family, spelled exactly as it
        -- appears in the source column. Verified against dimension_value_index
        -- at seed time; a member that does not exist is a configuration error,
        -- not something to match against.
        member_value    NVARCHAR(256) NOT NULL,

        -- 0 = system suggestion awaiting review, 1 = a human approved it.
        -- Nothing unconfirmed is treated as authoritative, consistent with
        -- semantic_table_config and semantic_snapshot_mapping.
        is_confirmed    BIT NOT NULL DEFAULT 0,

        created_at      DATETIME2 DEFAULT GETDATE(),
        updated_at      DATETIME2 DEFAULT GETDATE(),
        created_by      VARCHAR(50) NULL,
        updated_by      VARCHAR(50) NULL,

        CONSTRAINT uq_semantic_value_family
            UNIQUE (connection_id, dimension_id, family_name, member_value)
    );
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_value_family_lookup')
BEGIN
    CREATE INDEX ix_value_family_lookup
        ON semantic_value_family (connection_id, dimension_id, family_name);
END;
GO
