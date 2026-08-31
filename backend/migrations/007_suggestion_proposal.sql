-- ===========================================================================
-- 007_suggestion_proposal.sql
--
-- Gate 2 - give a generated suggestion somewhere to live.
--
-- Migration 006 stored the EVIDENCE behind a proposal: the profile, the sample
-- values, the reasoning, the confidence. It did not store the PROPOSAL itself.
--
-- The original design assumed proposals would sit in the configuration tables
-- as unconfirmed rows, but nothing writes there until a human presses Confirm.
-- So between being generated and being confirmed a proposal existed only in
-- memory, and the review screen had nothing durable to read - which is why it
-- was still wired to a development fixture whose made-up table name produced
-- "Column 'SalesData.CY' is not registered" when anyone tried to confirm.
--
-- Generating suggestions costs a full profiling pass and several model calls,
-- roughly four minutes for three tables. That cannot happen on every page load,
-- so it is done deliberately and the result is stored here.
--
-- Additive only. Rollback: 007_suggestion_proposal_rollback.sql
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- A stable handle for the proposal.
--
-- Confirm needs to address one specific proposal. Without this the API has to
-- rebuild a composite key from table and column names, which breaks for
-- table-level suggestions where column_name is NULL.
-- ---------------------------------------------------------------------------
IF COL_LENGTH('semantic_suggestion_evidence', 'suggestion_id') IS NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence ADD suggestion_id NVARCHAR(64) NULL;
END;
GO


-- ---------------------------------------------------------------------------
-- The proposal itself, as JSON.
--
-- Stored whole rather than spread across typed columns because a column-level
-- proposal and a table-level one carry different fields - classification and
-- dimension_role for one, temporal strategy and snapshot mappings for the other
-- - and splitting them would mean either two tables or a wide sparse one. The
-- shape is already agreed and validated in application code and by the CHECK
-- constraints on the configuration tables this eventually writes to, so the
-- database does not need to re-model it.
-- ---------------------------------------------------------------------------
IF COL_LENGTH('semantic_suggestion_evidence', 'proposal_json') IS NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence ADD proposal_json NVARCHAR(MAX) NULL;
END;
GO


-- ---------------------------------------------------------------------------
-- Whether a human has acted on it.
--
-- PENDING   - generated, nobody has looked
-- CONFIRMED - accepted, and written to the configuration tables
-- REJECTED  - explicitly declined
--
-- This is what makes a rejection survive a restart. Until now rejections were
-- held in a set in memory and lost whenever the container recycled, so the API
-- had to report them as "persisted: false".
-- ---------------------------------------------------------------------------
IF COL_LENGTH('semantic_suggestion_evidence', 'review_status') IS NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence ADD review_status NVARCHAR(20) NOT NULL
        CONSTRAINT df_suggestion_review_status DEFAULT 'PENDING';
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'reviewed_by') IS NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence ADD reviewed_by VARCHAR(50) NULL;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'reviewed_at') IS NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence ADD reviewed_at DATETIME2 NULL;
END;
GO

IF COL_LENGTH('semantic_suggestion_evidence', 'review_note') IS NULL
BEGIN
    ALTER TABLE semantic_suggestion_evidence ADD review_note NVARCHAR(512) NULL;
END;
GO


-- ---------------------------------------------------------------------------
-- Constrain the status, and index the two lookups the review screen performs:
-- a stable handle, and everything still pending for a connection.
-- ---------------------------------------------------------------------------
IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'ck_suggestion_review_status')
BEGIN
    ALTER TABLE semantic_suggestion_evidence
        ADD CONSTRAINT ck_suggestion_review_status
        CHECK (review_status IN ('PENDING', 'CONFIRMED', 'REJECTED'));
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_suggestion_handle')
BEGIN
    CREATE INDEX ix_suggestion_handle
        ON semantic_suggestion_evidence (suggestion_id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'ix_suggestion_pending')
BEGIN
    CREATE INDEX ix_suggestion_pending
        ON semantic_suggestion_evidence (connection_id, review_status);
END;
GO
