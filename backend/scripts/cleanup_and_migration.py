import sys
import os

# Setup path to backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import engine
from sqlalchemy import text

def clean_duplicate_models():
    print("--------------------------------------------------")
    print("1. RUNNING MODEL DUPLICATE CLEANUP")
    print("--------------------------------------------------")
    
    with engine.connect() as conn:
        # Find duplicate sets
        query = """
        SELECT provider_id, model_name, purpose, COUNT(model_id) AS cnt
        FROM llm_models
        GROUP BY provider_id, model_name, purpose
        HAVING COUNT(model_id) > 1
        """
        duplicates = conn.execute(text(query)).fetchall()
        
        if not duplicates:
            print("No duplicate model rows found in llm_models.")
            return
            
        for dup in duplicates:
            prov_id = dup.provider_id
            name = dup.model_name
            purp = dup.purpose
            print(f"\nProcessing duplicate group: Provider={prov_id}, Name='{name}', Purpose='{purp}'")
            
            # Fetch all model IDs in this duplicate group
            models_query = """
            SELECT model_id, is_default, is_active
            FROM llm_models
            WHERE provider_id = :prov_id AND model_name = :name AND purpose = :purp
            """
            model_rows = conn.execute(text(models_query), {"prov_id": prov_id, "name": name, "purp": purp}).fetchall()
            
            # Check which model IDs are referenced in fallbacks
            referenced_ids = []
            for m in model_rows:
                fallback_check = conn.execute(
                    text("SELECT COUNT(1) FROM llm_fallbacks WHERE model_id = :model_id"),
                    {"model_id": m.model_id}
                ).scalar()
                if fallback_check > 0:
                    referenced_ids.append(m.model_id)
            
            print(f"Total rows in DB: {len(model_rows)}")
            print(f"Model IDs referenced in llm_fallbacks: {referenced_ids}")
            
            # Decide which one to keep
            keep_id = None
            if len(referenced_ids) == 1:
                keep_id = referenced_ids[0]
                print(f"Keeping referenced Model ID: {keep_id}")
            elif len(referenced_ids) > 1:
                keep_id = referenced_ids[0]
                print(f"WARNING: Multiple rows referenced. Keeping first reference: {keep_id}")
            else:
                # None is referenced, keep the first one
                keep_id = model_rows[0].model_id
                print(f"No rows referenced in fallbacks. Keeping first Model ID: {keep_id}")
                
            # Delete the duplicates
            delete_ids = [m.model_id for m in model_rows if m.model_id != keep_id]
            print(f"Deleting duplicate Model IDs: {delete_ids}")
            
            if delete_ids:
                with engine.begin() as transaction_conn:
                    for d_id in delete_ids:
                        transaction_conn.execute(
                            text("DELETE FROM llm_models WHERE model_id = :d_id"),
                            {"d_id": d_id}
                        )
                print("Duplicates deleted successfully.")

def apply_database_constraints():
    print("\n--------------------------------------------------")
    print("2. APPLYING UNIQUE CONSTRAINTS AND INDEXES")
    print("--------------------------------------------------")
    
    with engine.begin() as conn:
        # Add UNIQUE constraint to llm_models
        model_constraint_sql = """
        IF NOT EXISTS (
            SELECT 1 
            FROM sys.objects 
            WHERE name = 'UQ_llm_models_provider_model_purpose' 
              AND type = 'UQ'
        )
        BEGIN
            ALTER TABLE llm_models 
            ADD CONSTRAINT UQ_llm_models_provider_model_purpose 
            UNIQUE (provider_id, model_name, purpose);
            PRINT 'Created UNIQUE constraint UQ_llm_models_provider_model_purpose';
        END
        ELSE
        BEGIN
            PRINT 'UNIQUE constraint UQ_llm_models_provider_model_purpose already exists';
        END
        """
        conn.execute(text(model_constraint_sql))
        
        # Add filtered unique index on llm_fallbacks for active routes
        fallback_index_sql = """
        IF NOT EXISTS (
            SELECT 1 
            FROM sys.indexes 
            WHERE name = 'UQ_llm_fallbacks_company_purpose_priority_active'
        )
        BEGIN
            CREATE UNIQUE INDEX UQ_llm_fallbacks_company_purpose_priority_active 
            ON llm_fallbacks(company_id, purpose, priority_order) 
            WHERE is_active = 1;
            PRINT 'Created UNIQUE filtered index UQ_llm_fallbacks_company_purpose_priority_active';
        END
        ELSE
        BEGIN
            PRINT 'UNIQUE filtered index UQ_llm_fallbacks_company_purpose_priority_active already exists';
        END
        """
        conn.execute(text(fallback_index_sql))

if __name__ == "__main__":
    clean_duplicate_models()
    apply_database_constraints()
