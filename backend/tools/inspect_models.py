from services.fallback_service import FallbackService

company_id = "FD4925A0-9034-4343-A368-8D20A919DF92"

models_intent = FallbackService.get_models_for_purpose("INTENT_CLASSIFICATION", company_id=company_id)
print("Intent classification models:")
print(models_intent)

models_sql = FallbackService.get_models_for_purpose("SQL_GENERATION", company_id=company_id)
print("\nSQL generation models:")
print(models_sql)
