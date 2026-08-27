import logging
from database import engine
from sqlalchemy import text

def run_migration():
    with engine.begin() as conn:
        # 1. Seed Permissions in permissions table (DML operation)
        permissions = [
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
        ]

        print("Seeding permissions into database...")
        for name, desc, cat in permissions:
            conn.execute(text("""
                IF NOT EXISTS (SELECT 1 FROM permissions WHERE permission_name = :name)
                    INSERT INTO permissions (permission_name, description, category)
                    VALUES (:name, :desc, :cat)
            """), {"name": name, "desc": desc, "cat": cat})
        print("Permissions seeded.")

        # 2. Assign to SUPER_ADMIN, ADMIN, ANALYST
        super_admin_row = conn.execute(text("SELECT id FROM roles WHERE role_name = 'SUPER_ADMIN'")).fetchone()
        admin_row       = conn.execute(text("SELECT id FROM roles WHERE role_name = 'ADMIN'")).fetchone()
        analyst_row     = conn.execute(text("SELECT id FROM roles WHERE role_name = 'ANALYST'")).fetchone()

        if super_admin_row:
            sa_id = super_admin_row.id
            conn.execute(text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT :sa_id, id FROM permissions p
                WHERE NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = :sa_id AND rp.permission_id = p.id)
            """), {"sa_id": sa_id})
            print("Assigned all permissions to SUPER_ADMIN.")

        if admin_row:
            a_id = admin_row.id
            conn.execute(text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT :a_id, id FROM permissions p
                WHERE p.permission_name IN (
                    'page:overview:v', 'page:overview:m',
                    'page:chat:v', 'page:chat:m',
                    'page:schema:v', 'page:schema:m',
                    'page:semantic:v', 'page:semantic:m',
                    'page:users:v', 'page:users:m',
                    'page:audit:v', 'page:audit:m',
                    'chat:ask', 'chat:history', 'chat:delete'
                )
                AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = :a_id AND rp.permission_id = p.id)
            """), {"a_id": a_id})
            print("Assigned permissions to ADMIN.")

        if analyst_row:
            an_id = analyst_row.id
            conn.execute(text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT :an_id, id FROM permissions p
                WHERE p.permission_name IN (
                    'page:chat:v', 'page:chat:m',
                    'page:schema:v',
                    'page:semantic:v',
                    'chat:ask', 'chat:history'
                )
                AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = :an_id AND rp.permission_id = p.id)
            """), {"an_id": an_id})
            print("Assigned permissions to ANALYST.")

    print("Permissions seed completed successfully!")

if __name__ == "__main__":
    run_migration()
