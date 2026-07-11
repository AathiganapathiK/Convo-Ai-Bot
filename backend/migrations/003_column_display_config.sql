CREATE TABLE column_display_config
(
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    connection_id UNIQUEIDENTIFIER NOT NULL
        REFERENCES database_connections(connection_id),

    table_name NVARCHAR(128) NOT NULL,

    column_name NVARCHAR(128) NOT NULL,

    is_visible BIT NOT NULL DEFAULT 1,

    display_label NVARCHAR(128) NULL,

    column_type NVARCHAR(30) NOT NULL DEFAULT 'dimension',

    created_at DATETIME2 DEFAULT GETDATE(),

    CONSTRAINT uq_column_display
    UNIQUE
    (
        connection_id,
        table_name,
        column_name
    )
);