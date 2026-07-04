-- ============================================================================
-- Enterprise Security Framework — Database Migration
-- Database: adv_works (SQL Server)
-- ============================================================================

-- ============================================================================
-- 1. ROLES TABLE
-- ============================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'roles')
BEGIN
    CREATE TABLE roles (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        role_name   VARCHAR(50) NOT NULL UNIQUE,
        description VARCHAR(255),
        is_active   BIT DEFAULT 1,
        created_at  DATETIME DEFAULT GETDATE(),
        updated_at  DATETIME DEFAULT GETDATE()
    );

    INSERT INTO roles (role_name, description) VALUES
        ('SUPER_ADMIN', 'Full system access including role and security management'),
        ('ADMIN',       'User management and audit access'),
        ('ANALYST',     'Query and export access with RLS/CLS restrictions');
END;
GO


-- ============================================================================
-- 2. PERMISSIONS TABLE
-- ============================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'permissions')
BEGIN
    CREATE TABLE permissions (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        permission_name VARCHAR(100) NOT NULL UNIQUE,
        description     VARCHAR(255),
        category        VARCHAR(50),
        created_at      DATETIME DEFAULT GETDATE()
    );

    INSERT INTO permissions (permission_name, description, category) VALUES
        ('chat:query',          'Submit analytical queries',             'chat'),
        ('chat:export',         'Export query results to Excel',         'chat'),
        ('chat:history:read',   'View own query history',               'chat'),
        ('admin:users:read',    'View user list',                       'admin'),
        ('admin:users:write',   'Create and update users',              'admin'),
        ('admin:users:delete',  'Delete user accounts',                 'admin'),
        ('admin:roles:manage',  'Manage roles and permissions',         'admin'),
        ('admin:audit:read',    'View audit logs',                      'admin'),
        ('security:rls:manage', 'Manage row-level security rules',      'security'),
        ('security:cls:manage', 'Manage column-level security rules',   'security'),
        ('system:debug',        'Access debug and test endpoints',      'system');
END;
GO


-- ============================================================================
-- 3. ROLE_PERMISSIONS TABLE (many-to-many)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'role_permissions')
BEGIN
    CREATE TABLE role_permissions (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        role_id         INT NOT NULL REFERENCES roles(id),
        permission_id   INT NOT NULL REFERENCES permissions(id),
        created_at      DATETIME DEFAULT GETDATE(),
        UNIQUE (role_id, permission_id)
    );

    -- SUPER_ADMIN: all permissions
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT
        (SELECT id FROM roles WHERE role_name = 'SUPER_ADMIN'),
        id
    FROM permissions;

    -- ADMIN: chat + admin (not security/system)
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT
        (SELECT id FROM roles WHERE role_name = 'ADMIN'),
        id
    FROM permissions
    WHERE permission_name IN (
        'chat:query', 'chat:export', 'chat:history:read',
        'admin:users:read', 'admin:users:write', 'admin:audit:read'
    );

    -- ANALYST: chat only
    INSERT INTO role_permissions (role_id, permission_id)
    SELECT
        (SELECT id FROM roles WHERE role_name = 'ANALYST'),
        id
    FROM permissions
    WHERE permission_name IN (
        'chat:query', 'chat:export', 'chat:history:read'
    );
END;
GO


-- ============================================================================
-- 4. AUDIT_LOGS TABLE
-- ============================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'audit_logs')
BEGIN
    CREATE TABLE audit_logs (
        id              BIGINT IDENTITY(1,1) PRIMARY KEY,
        user_id         VARCHAR(50),
        action_type     VARCHAR(50) NOT NULL,
        resource        VARCHAR(255),
        query_text      NVARCHAR(MAX),
        generated_sql   NVARCHAR(MAX),
        status          VARCHAR(50) DEFAULT 'SUCCESS',
        ip_address      VARCHAR(45),
        metadata        NVARCHAR(MAX),
        created_at      DATETIME DEFAULT GETDATE()
    );

    CREATE INDEX IX_audit_logs_user_id    ON audit_logs(user_id);
    CREATE INDEX IX_audit_logs_action     ON audit_logs(action_type);
    CREATE INDEX IX_audit_logs_created    ON audit_logs(created_at);
END;
GO


-- ============================================================================
-- 5. USER_DATA_ACCESS TABLE (RLS)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'user_data_access')
BEGIN
    CREATE TABLE user_data_access (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        employee_id     VARCHAR(50) NOT NULL,
        access_type     VARCHAR(50) NOT NULL,    -- 'REGION' or 'SALESPERSON'
        access_value    VARCHAR(255) NOT NULL,   -- the SalesTerritoryKey or EmployeeKey value
        created_at      DATETIME DEFAULT GETDATE(),
        created_by      VARCHAR(50)
    );

    CREATE INDEX IX_uda_employee ON user_data_access(employee_id);
    CREATE INDEX IX_uda_type     ON user_data_access(access_type);
END;
GO


-- ============================================================================
-- 6. ROLE_COLUMN_ACCESS TABLE (CLS)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'role_column_access')
BEGIN
    CREATE TABLE role_column_access (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        role_id         INT NOT NULL REFERENCES roles(id),
        table_name      VARCHAR(128) NOT NULL,
        column_name     VARCHAR(128) NOT NULL,
        is_allowed      BIT DEFAULT 1,
        created_at      DATETIME DEFAULT GETDATE(),
        UNIQUE (role_id, table_name, column_name)
    );

    -- SUPER_ADMIN / ADMIN: full access (no restrictions = allow all)
    -- ANALYST: define allowed columns per table

    DECLARE @analyst_role_id INT = (SELECT id FROM roles WHERE role_name = 'ANALYST');

    -- Sales table — allowed columns for ANALYST
    INSERT INTO role_column_access (role_id, table_name, column_name, is_allowed) VALUES
        (@analyst_role_id, 'Sales', 'OrderDate',          1),
        (@analyst_role_id, 'Sales', 'Sales',              1),
        (@analyst_role_id, 'Sales', 'Quantity',           1),
        (@analyst_role_id, 'Sales', 'UnitPrice',          1),
        (@analyst_role_id, 'Sales', 'ProductKey',         1),
        (@analyst_role_id, 'Sales', 'SalesTerritoryKey',  1),
        (@analyst_role_id, 'Sales', 'Cost',               0),  -- restricted

        -- Products table
        (@analyst_role_id, 'Products', 'ProductKey',      1),
        (@analyst_role_id, 'Products', 'Product',         1),
        (@analyst_role_id, 'Products', 'Category',        1),
        (@analyst_role_id, 'Products', 'Subcategory',     1),

        -- Region table
        (@analyst_role_id, 'Region', 'SalesTerritoryKey', 1),
        (@analyst_role_id, 'Region', 'Region',            1),
        (@analyst_role_id, 'Region', 'Country',           1),

        -- Salesperson table
        (@analyst_role_id, 'Salesperson', 'EmployeeKey',  1),
        (@analyst_role_id, 'Salesperson', 'Salesperson',  1),
        (@analyst_role_id, 'Salesperson', 'Title',        1),

        -- Reseller table
        (@analyst_role_id, 'Reseller', 'ResellerKey',     1),
        (@analyst_role_id, 'Reseller', 'Reseller',        1),
        (@analyst_role_id, 'Reseller', 'Business_Type',   1),

        -- Targets table
        (@analyst_role_id, 'Targets', 'EmployeeKey',      1),
        (@analyst_role_id, 'Targets', 'Target',           1),
        (@analyst_role_id, 'Targets', 'TargetMonth',      1);
END;
GO


-- ============================================================================
-- 7. ADD role_id FK TO EXISTING users TABLE (backward compatible)
-- ============================================================================

IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'users' AND COLUMN_NAME = 'role_id'
)
BEGIN
    ALTER TABLE users ADD role_id INT NULL;
END;
GO

-- Back-fill role_id from existing role text column
UPDATE u
SET u.role_id = r.id
FROM users u
INNER JOIN roles r ON r.role_name = u.role
WHERE u.role_id IS NULL;
GO


-- ============================================================================
-- 8. ENSURE SYSTEM TABLES EXIST (chat_sessions, chat_messages, etc.)
-- ============================================================================

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'chat_sessions')
BEGIN
    CREATE TABLE chat_sessions (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        employee_id     VARCHAR(50) NOT NULL,
        session_name    VARCHAR(255) NOT NULL,
        created_at      DATETIME DEFAULT GETDATE(),
        updated_at      DATETIME DEFAULT GETDATE()
    );
END;
GO

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'chat_messages')
BEGIN
    CREATE TABLE chat_messages (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        session_id          INT NOT NULL REFERENCES chat_sessions(id),
        role                VARCHAR(20) NOT NULL,
        message_text        NVARCHAR(MAX),
        sql_query           NVARCHAR(MAX),
        business_summary    NVARCHAR(MAX),
        result_data         NVARCHAR(MAX),
        created_at          DATETIME DEFAULT GETDATE()
    );
END;
GO

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'user_queries')
BEGIN
    CREATE TABLE user_queries (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        employee_id         VARCHAR(50) NOT NULL,
        session_id          INT,
        question            NVARCHAR(MAX),
        sql_query           NVARCHAR(MAX),
        execution_status    VARCHAR(50),
        execution_time      FLOAT,
        created_at          DATETIME DEFAULT GETDATE()
    );
END;
GO

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'user_usage')
BEGIN
    CREATE TABLE user_usage (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        employee_id         VARCHAR(50) NOT NULL,
        session_id          INT,
        request_type        VARCHAR(50),
        prompt_tokens       INT,
        completion_tokens   INT,
        total_tokens        INT,
        estimated_cost      FLOAT,
        created_at          DATETIME DEFAULT GETDATE()
    );
END;
GO

PRINT '=== Security Framework Migration Complete ===';
GO


select *
from users;