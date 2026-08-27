-- ===========================================================================
-- 006_suggestion_evidence.sql
--
-- Gate 2 - evidence behind a configuration suggestion.
--
-- Migration 004 gave every configuration row an is_confirmed flag, so a pending
-- suggestion is simply a row that nobody has approved yet. That works for the
-- answer but leaves nowhere for the reasoning: no sample values, no distinct
-- count, no confidence, no explanation.
--
-- Step 10's review screen has to show a person WHY the system proposed
-- something - the actual values it looked at - otherwise a reviewer clicks
-- approve on 120 columns without reading and we have built an elaborate way to
-- rubber-stamp machine guesses. This table is where that evidence lives.
--
-- Numbering note: 005 is deliberately skipped. 004_access_control_extension.sql
-- exists on disk unregistered and unapplied; 005 is left free for it so the
-- sequence stays unambiguous without this migration touching that file.
--
-- Additive only. Rollback: 006_suggestion_evidence_rollback.sql
-- ===========================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'semantic_suggestion_evidence')
BEGIN
    CREATE TABLE semantic_suggestion_evidence
    (
        evidence_id         UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

        connection_id       UNIQUEIDENTIFIER NOT NULL
                            REFERENCES database_connections(connection_id),

        table_name          NVARCHAR(128) NOT NULL,

        -- NULL means the suggestion is about the table as a whole (its domain,
        -- temporal strategy, snapshot mapping) rather than about one column.
        column_name         NVARCHAR(128) NULL,

        -- --- the profile the suggestion was derived from -------------------
        data_type           NVARCHAR(64) NULL,
        distinct_count      INT NULL,
        row_count_profiled  INT NULL,
        null_fraction       FLOAT NULL,

        -- JSON array of sample values, e.g. ["A April","B May","C June"].
        -- Only ever populated for low-cardinality columns. High-cardinality
        -- columns hold customer and manager names, so their values are never
        -- sent to a model and never stored here.
        sample_values       NVARCHAR(MAX) NULL,

        samples_withheld    BIT NOT NULL DEFAULT 0,

        -- Why samples were withheld, so the screen can say "8,412 distinct
        -- values, likely personal names" instead of rendering an empty box
        -- that looks like a bug.
        withheld_reason     NVARCHAR(256) NULL,

        -- --- what the model concluded --------------------------------------
        confidence          FLOAT NULL,
        reasoning           NVARCHAR(MAX) NULL,

        -- Which model produced this, e.g. 'llm:openai/gpt-oss-120b'. Recorded
        -- so a suggestion can be re-examined when the model changes.
        suggested_by        NVARCHAR(128) NULL,

        suggested_at        DATETIME2 DEFAULT GETDATE(),

        -- One row per thing being suggested about. Re-running the suggester
        -- overwrites rather than accumulating duplicates.
        CONSTRAINT uq_suggestion_evidence
            UNIQUE (connection_id, table_name, column_name),

        CONSTRAINT ck_evidence_confidence
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),

        CONSTRAINT ck_evidence_null_fraction
            CHECK (null_fraction IS NULL OR (null_fraction >= 0 AND null_fraction <= 1)),

        CONSTRAINT ck_evidence_distinct_count
            CHECK (distinct_count IS NULL OR distinct_count >= 0),

        -- If samples were withheld there must be a reason, otherwise the screen
        -- has nothing to explain the empty evidence box with.
        CONSTRAINT ck_evidence_withheld_reason
            CHECK (samples_withheld = 0 OR withheld_reason IS NOT NULL)
    );
END;
GO


-- Lookup path used by the review screen: everything pending for one connection,
-- ordered by table.
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_suggestion_evidence_lookup')
BEGIN
    CREATE INDEX ix_suggestion_evidence_lookup
        ON semantic_suggestion_evidence (connection_id, table_name);
END;
GO
