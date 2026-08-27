import sys
import os
import json
import time

# Ensure backend root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app
from database import engine
from sqlalchemy import text
from services.conversation_memory import (
    get_pending_clarification,
    clear_pending_clarification,
    set_pending_clarification
)

class DummyRequest:
    class DummyClient:
        host = "127.0.0.1"
    client = DummyClient()

request = DummyRequest()
user = {
    "employee_id": "EMP_LIVE_VERIFY",
    "company_id": "FD4925A0-9034-4343-A368-8D20A919DF92", # Matches existing company in DB
    "role": "ANALYST",
    "official_email": "analyst@company.com"
}

session_id = None

def setup_live_session():
    global session_id
    with engine.begin() as conn:
        res = conn.execute(
            text("""
                INSERT INTO chat_sessions (employee_id, session_name)
                OUTPUT INSERTED.id
                VALUES (:emp, :name)
            """),
            {
                "emp": user["employee_id"],
                "name": "Live Verify Session"
            }
        )
        session_id = res.scalar()
        print(f"Created temporary session with ID: {session_id}")

def cleanup_live_session():
    if session_id:
        with engine.begin() as conn:
            # Delete messages first
            conn.execute(
                text("DELETE FROM chat_messages WHERE session_id = :sid"),
                {"sid": session_id}
            )
            # Delete session
            conn.execute(
                text("DELETE FROM chat_sessions WHERE id = :sid"),
                {"sid": session_id}
            )
            print(f"Cleaned up temporary session ID: {session_id}")

def reset_session():
    clear_pending_clarification(user["employee_id"], str(session_id))

def test_initial_question():
    print("\n--- 1. Testing Initial Question ---")
    reset_session()
    response = app.ask_question(
        question="Show cotton pant sales",
        session_id=session_id,
        request=request,
        user=user
    )
    if hasattr(response, "status_code") and response.status_code != 200:
        body = response.body.decode("utf-8")
        print(f"Status: {response.status_code}")
        print(f"Response: {body}")
        return None
    print(f"Response keys: {response.keys() if isinstance(response, dict) else 'None'}")
    if isinstance(response, dict) and "error" in response:
        print(f"Error payload: {response['error']}")
    elif hasattr(response, "body"):
        print(f"Response body: {response.body.decode('utf-8')}")
    else:
        print(f"Response: {json.dumps(response, indent=2)}")
    return response

def test_selection(selection):
    print(f"\n--- 2. Testing Selection: '{selection}' ---")
    response = app.ask_question(
        question=selection,
        session_id=session_id,
        request=request,
        user=user
    )
    if hasattr(response, "status_code"):
        body = response.body.decode("utf-8")
        print(f"Status: {response.status_code}")
        print(f"Response: {body}")
    else:
        print(f"Response keys: {response.keys() if isinstance(response, dict) else 'None'}")
        if isinstance(response, dict) and "error" in response:
            print(f"Error payload: {response['error']}")
        else:
            print(f"Response Summary: {response.get('business_summary') if isinstance(response, dict) else ''}")
            print(f"Generated SQL: {response.get('sql_query') if isinstance(response, dict) else ''}")
    
    # Check if pending clarification was cleared
    state = get_pending_clarification(user["employee_id"], str(session_id))
    print(f"Remaining Stored State: {state is not None}")

if __name__ == "__main__":
    print("Starting Live Clarification Verification...")
    try:
        setup_live_session()
        
        # Step 1: Initial Question
        test_initial_question()
        
        # Step 2: Test MENS PYJAMA PANT
        test_selection("MENS PYJAMA PANT")
        
        # Step 3: Test numeric "1" selection
        test_initial_question()
        test_selection("1")
        
        # Step 4: Test "option 2" selection
        test_initial_question()
        test_selection("option 2")
        
        # Step 5: Test invalid "999"
        test_initial_question()
        test_selection("999")
        
        # Step 6: Test ambiguous "ls"
        test_initial_question()
        test_selection("ls")
        
    finally:
        reset_session()
        cleanup_live_session()
