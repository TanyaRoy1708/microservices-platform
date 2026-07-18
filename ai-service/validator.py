ALLOWED_SERVICES = {"users", "orders"}
ALLOWED_OPERATIONS = {
    "users": {"list_users", "find_user_by_name", "find_users_by_city"},
    "orders": {"list_orders", "find_orders_by_status", "find_orders_by_user"}
}
ALLOWED_FILTERS = {
    "users": {"name", "city"},
    "orders": {"status", "user_id", "user_name"}
}

def validate_intent(intent: dict) -> tuple[bool, str]:
    if "service" not in intent or "operation" not in intent:
        return False, "Missing service or operation"
    
    svc = intent["service"]
    if svc not in ALLOWED_SERVICES:
        return False, f"Unknown service {svc}"
    
    if intent["operation"] not in ALLOWED_OPERATIONS[svc]:
        return False, f"Unknown operation {intent['operation']}"
        
    for key in intent.get("filters", {}):
        if key not in ALLOWED_FILTERS[svc]:
            return False, f"Unknown filter {key}"
            
    return True, ""
