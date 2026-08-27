-- ============================================================================
-- Enterprise Access Control Extension (RBAC, Page V/M, Chat A/H/D, Scopes)
-- Database: SQL Server
-- ============================================================================

-- 1. ADD division_code COLUMN TO dbo.chat_sessions IF NOT EXISTS
IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'chat_sessions')
BEGIN
    IF NOT EXISTS (
        SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = 'chat_sessions' AND COLUMN_NAME = 'division_code'
    )
    BEGIN
        ALTER TABLE dbo.chat_sessions ADD division_code VARCHAR(50) NULL;
    END;
END;
GO

-- Backfill division_code in chat_sessions from user_division_access if chat_sessions exists
IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'chat_sessions')
BEGIN
    UPDATE cs
    SET cs.division_code = uda.division_code
    FROM dbo.chat_sessions cs
    INNER JOIN dbo.users u ON u.employee_id = cs.employee_id
    INNER JOIN dbo.user_division_access uda ON u.id = uda.user_id
    WHERE cs.division_code IS NULL;
END;
GO


-- 2. USER_PERMISSION_OVERRIDES TABLE
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'user_permission_overrides')
BEGIN
    CREATE TABLE dbo.user_permission_overrides (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        user_id         INT NOT NULL REFERENCES dbo.users(id),
        permission_id   INT NOT NULL REFERENCES dbo.permissions(id),
        is_granted      BIT NOT NULL DEFAULT 1,
        created_at      DATETIME DEFAULT GETDATE(),
        created_by      VARCHAR(50),
        UNIQUE (user_id, permission_id)
    );

    CREATE INDEX IX_upo_user ON dbo.user_permission_overrides(user_id);
END;
GO


-- 3. ROLE_DATA_ACCESS TABLE (Role-level Region, Product, Channel, Division scopes)
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'role_data_access')
BEGIN
    CREATE TABLE dbo.role_data_access (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        role_id         INT NOT NULL REFERENCES dbo.roles(id),
        access_type     VARCHAR(50) NOT NULL, -- 'DIVISION', 'REGION', 'PRODUCT', 'CHANNEL'
        access_value    VARCHAR(255) NOT NULL,
        created_at      DATETIME DEFAULT GETDATE(),
        created_by      VARCHAR(50),
        UNIQUE (role_id, access_type, access_value)
    );

    CREATE INDEX IX_rda_role ON dbo.role_data_access(role_id);
END;
GO


-- 4. SEED V/M PAGE & A/H/D CHAT PERMISSIONS
INSERT INTO dbo.permissions (permission_name, description, category)
SELECT v.permission_name, v.description, v.category
FROM (VALUES
    ('page:overview:v',     'View Overview Page',          'page_view'),
    ('page:overview:m',     'Modify Overview Settings',    'page_modify'),
    ('page:chat:v',         'View Chat Page',              'page_view'),
    ('page:chat:m',         'Modify Chat Settings',        'page_modify'),
    ('page:connections:v',  'View Data Sources',           'page_view'),
    ('page:connections:m',  'Modify Data Sources',         'page_modify'),
    ('page:schema:v',       'View Schema Discovery',       'page_view'),
    ('page:schema:m',       'Modify Schema Discovery',     'page_modify'),
    ('page:semantic:v',     'View Semantic Layer',         'page_view'),
    ('page:semantic:m',     'Modify Semantic Layer',       'page_modify'),
    ('page:providers:v',    'View AI Providers',           'page_view'),
    ('page:providers:m',    'Modify AI Providers',         'page_modify'),
    ('page:prompts:v',      'View Prompt Studio',          'page_view'),
    ('page:prompts:m',      'Modify Prompt Studio',        'page_modify'),
    ('page:intents:v',      'View Intent Configuration',   'page_view'),
    ('page:intents:m',      'Modify Intent Configuration', 'page_modify'),
    ('page:users:v',        'View User Management',        'page_view'),
    ('page:users:m',        'Modify User Management',      'page_modify'),
    ('page:roles:v',        'View Role Management',        'page_view'),
    ('page:roles:m',        'Modify Role Management',      'page_modify'),
    ('page:audit:v',        'View Audit Logs',             'page_view'),
    ('page:audit:m',        'Modify Audit Settings',       'page_modify'),
    ('chat:ask',            'Ask Chatbot (A)',             'chat_action'),
    ('chat:history',        'View Chat History (H)',       'chat_action'),
    ('chat:delete',         'Delete Chat Sessions (D)',    'chat_action')
) AS v(permission_name, description, category)
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.permissions p WHERE p.permission_name = v.permission_name
);
GO


-- 5. SEED DEFAULT PERMISSIONS FOR SUPER_ADMIN, ADMIN, ANALYST
DECLARE @super_admin_id INT = (SELECT id FROM dbo.roles WHERE role_name = 'SUPER_ADMIN');
DECLARE @admin_id INT       = (SELECT id FROM dbo.roles WHERE role_name = 'ADMIN');
DECLARE @analyst_id INT     = (SELECT id FROM dbo.roles WHERE role_name = 'ANALYST');

-- Assign all permissions to SUPER_ADMIN
IF @super_admin_id IS NOT NULL
BEGIN
    INSERT INTO dbo.role_permissions (role_id, permission_id)
    SELECT @super_admin_id, p.id
    FROM dbo.permissions p
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.role_permissions rp WHERE rp.role_id = @super_admin_id AND rp.permission_id = p.id
    );
END;

-- Assign ADMIN permissions (Overview, Chat, Users, Audit, Schema, Semantic + Ask/History/Delete)
IF @admin_id IS NOT NULL
BEGIN
    INSERT INTO dbo.role_permissions (role_id, permission_id)
    SELECT @admin_id, p.id
    FROM dbo.permissions p
    WHERE p.permission_name IN (
        'page:overview:v', 'page:overview:m',
        'page:chat:v', 'page:chat:m',
        'page:schema:v', 'page:schema:m',
        'page:semantic:v', 'page:semantic:m',
        'page:users:v', 'page:users:m',
        'page:audit:v', 'page:audit:m',
        'chat:ask', 'chat:history', 'chat:delete'
    )
    AND NOT EXISTS (
        SELECT 1 FROM dbo.role_permissions rp WHERE rp.role_id = @admin_id AND rp.permission_id = p.id
    );
END;

-- Assign ANALYST permissions (Chat, Schema, Semantic + Ask/History)
IF @analyst_id IS NOT NULL
BEGIN
    INSERT INTO dbo.role_permissions (role_id, permission_id)
    SELECT @analyst_id, p.id
    FROM dbo.permissions p
    WHERE p.permission_name IN (
        'page:chat:v', 'page:chat:m',
        'page:schema:v',
        'page:semantic:v',
        'chat:ask', 'chat:history'
    )
    AND NOT EXISTS (
        SELECT 1 FROM dbo.role_permissions rp WHERE rp.role_id = @analyst_id AND rp.permission_id = p.id
    );
END;
GO
