import unittest
from unittest.mock import patch, MagicMock

from services.conversation_memory import (
    conversation_store,
    pending_clarification_store,
    get_history,
    add_exchange,
    hydrate_history_from_db,
    get_pending_clarification,
    set_pending_clarification,
    MAX_HISTORY
)


class TestConversationMemoryHardening(unittest.TestCase):

    def setUp(self):
        conversation_store.clear()
        pending_clarification_store.clear()

    def test_1_cache_hit(self):
        """TEST 1 — CACHE HIT: Existing conversation_store state returned without DB query."""
        add_exchange("EMP_001", "Show sales", "SELECT SUM(CY) FROM Sales", "101")
        
        with patch("services.conversation_memory.hydrate_history_from_db") as mock_hydrate:
            hist = get_history("EMP_001", "101")
            self.assertEqual(len(hist), 1)
            self.assertEqual(hist[0]["question"], "Show sales")
            mock_hydrate.assert_not_called()

    @patch("database.engine.connect")
    def test_2_cache_miss_hydration(self, mock_connect):
        """TEST 2 — CACHE MISS / HYDRATION: Empty memory hydrates from SQL Server."""
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock session check and chat_messages
        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("EMP_001", "COMP_A")),  # session ownership check
            MagicMock(fetchall=lambda: [                       # recent messages (ORDER BY id DESC)
                MagicMock(_mapping={"id": 2, "role": "ASSISTANT", "message_text": "Summary", "sql_query": "SELECT SUM(CY) FROM Sales", "created_at": "2026-08-19"}),
                MagicMock(_mapping={"id": 1, "role": "USER", "message_text": "Show sales", "sql_query": None, "created_at": "2026-08-19"})
            ])
        ]

        hist = get_history("EMP_001", "101", company_id="COMP_A")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["question"], "Show sales")
        self.assertEqual(hist[0]["sql_query"], "SELECT SUM(CY) FROM Sales")
        # Verify populated cache
        self.assertIn("101", conversation_store["EMP_001"])

    @patch("database.engine.connect")
    def test_3_empty_chat(self, mock_connect):
        """TEST 3 — EMPTY CHAT: No messages in DB returns empty list without error."""
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("EMP_001", "COMP_A")),
            MagicMock(fetchall=lambda: [])
        ]

        hist = get_history("EMP_001", "102", company_id="COMP_A")
        self.assertEqual(len(hist), 0)

    @patch("database.engine.connect")
    def test_4_new_chat(self, mock_connect):
        """TEST 4 — NEW CHAT: Chat A has history, Chat B is new and starts empty."""
        add_exchange("EMP_001", "Chat A question", "SQL A", "101")
        
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("EMP_001", "COMP_A")),
            MagicMock(fetchall=lambda: [])
        ]

        hist_b = get_history("EMP_001", "102", company_id="COMP_A")
        self.assertEqual(len(hist_b), 0)
        self.assertEqual(len(get_history("EMP_001", "101")), 1)

    def test_5_chat_switch(self):
        """TEST 5 — CHAT SWITCH: Independent history maintained across sessions."""
        add_exchange("EMP_001", "Show cotton", "SQL Cotton", "101")
        add_exchange("EMP_001", "Show linen", "SQL Linen", "102")

        self.assertEqual(get_history("EMP_001", "101")[0]["question"], "Show cotton")
        self.assertEqual(get_history("EMP_001", "102")[0]["question"], "Show linen")
        self.assertEqual(get_history("EMP_001", "101")[0]["question"], "Show cotton")

    @patch("database.engine.connect")
    def test_6_refresh_restart(self, mock_connect):
        """TEST 6 — REFRESH/RESTART: Clearing in-memory store triggers DB hydration."""
        add_exchange("EMP_001", "Show cotton", "SQL Cotton", "101")
        conversation_store.clear()  # Simulate backend restart

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("EMP_001", "COMP_A")),
            MagicMock(fetchall=lambda: [
                MagicMock(_mapping={"id": 2, "role": "ASSISTANT", "message_text": "Cotton Summary", "sql_query": "SQL Cotton", "created_at": "2026-08-19"}),
                MagicMock(_mapping={"id": 1, "role": "USER", "message_text": "Show cotton", "sql_query": None, "created_at": "2026-08-19"})
            ])
        ]

        hist = get_history("EMP_001", "101", company_id="COMP_A")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["question"], "Show cotton")

    @patch("database.engine.connect")
    def test_7_user_isolation(self, mock_connect):
        """TEST 7 — USER ISOLATION: User A cannot hydrate User B's chat."""
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        # Session 101 belongs to User B ("EMP_002")
        mock_conn.execute.return_value.fetchone.return_value = None  # WHERE employee_id = EMP_001 returns None

        # User A ("EMP_001") attempts hydration on Session 101
        hydrated = hydrate_history_from_db("EMP_001", "101", company_id="COMP_A")
        # Since DB ownership check fails for EMP_001, User A receives []
        self.assertEqual(len(hydrated), 0)

    @patch("database.engine.connect")
    def test_8_company_isolation(self, mock_connect):
        """TEST 8 — COMPANY ISOLATION: Company A cannot hydrate Company B's chat."""
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        # Session 101 belongs to COMP_B
        mock_conn.execute.return_value.fetchone.return_value = None  # WHERE company_id = COMP_A returns None

        hydrated = hydrate_history_from_db("EMP_001", "101", company_id="COMP_A")
        self.assertEqual(len(hydrated), 0)

    @patch("database.engine.connect")
    def test_9_super_admin_hydration(self, mock_connect):
        """TEST 9 — SUPER_ADMIN: SUPER_ADMIN accesses target user's session and gets target history."""
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        
        # Session 101 belongs to target user EMP_005
        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("EMP_005", "COMP_A")),
            MagicMock(fetchall=lambda: [
                MagicMock(_mapping={"id": 2, "role": "ASSISTANT", "message_text": "Summary", "sql_query": "SQL Target", "created_at": "2026-08-19"}),
                MagicMock(_mapping={"id": 1, "role": "USER", "message_text": "Target Question", "sql_query": None, "created_at": "2026-08-19"})
            ])
        ]

        # In app.py, target owner EMP_005 is passed to get_history when SUPER_ADMIN requests session 101
        hist = get_history("EMP_005", "101", company_id="COMP_A")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["question"], "Target Question")

    def test_10_super_admin_wrong_user_bug_prevention(self):
        """TEST 10 — SUPER_ADMIN WRONG USER BUG: History lookup key uses target owner ID."""
        target_owner_id = "EMP_005"
        super_admin_id = "EMP_001"
        
        add_exchange(target_owner_id, "Owner question", "SQL Owner", "101")
        
        # When app.py passes target_owner_id ("EMP_005"), history is correctly retrieved
        hist = get_history(target_owner_id, "101")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["question"], "Owner question")
        
        # Verify super_admin_id key remains empty
        self.assertEqual(len(conversation_store[super_admin_id]["101"]), 0)

    @patch("database.engine.connect")
    def test_11_history_limit(self, mock_connect):
        """TEST 11 — HISTORY LIMIT: Truncates to MAX_HISTORY (5) in chronological order."""
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Create 14 messages (7 exchanges: Q1..Q7).
        # Query SELECT TOP 10 ORDER BY id DESC returns the 10 most recent messages (exchanges Q3..Q7) in DESC order:
        desc_db_messages = []
        for i in range(7, 2, -1):
            desc_db_messages.append(MagicMock(_mapping={"id": i * 2, "role": "ASSISTANT", "message_text": f"Ans {i}", "sql_query": f"SQL {i}", "created_at": "2026-08-19"}))
            desc_db_messages.append(MagicMock(_mapping={"id": i * 2 - 1, "role": "USER", "message_text": f"Q {i}", "sql_query": None, "created_at": "2026-08-19"}))

        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("EMP_001", "COMP_A")),
            MagicMock(fetchall=lambda: desc_db_messages)
        ]

        hist = get_history("EMP_001", "101", company_id="COMP_A")
        self.assertEqual(len(hist), MAX_HISTORY)
        self.assertEqual(hist[0]["question"], "Q 3")
        self.assertEqual(hist[-1]["question"], "Q 7")

    @patch("database.engine.connect")
    def test_12_repeated_request_cache_usage(self, mock_connect):
        """TEST 12 — REPEATED REQUEST: First request hydrates, second uses cache without duplicate entries."""
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("EMP_001", "COMP_A")),
            MagicMock(fetchall=lambda: [
                MagicMock(_mapping={"id": 2, "role": "ASSISTANT", "message_text": "Summary", "sql_query": "SQL 1", "created_at": "2026-08-19"}),
                MagicMock(_mapping={"id": 1, "role": "USER", "message_text": "Q 1", "sql_query": None, "created_at": "2026-08-19"})
            ])
        ]

        # Request 1: Hydrates
        hist1 = get_history("EMP_001", "101", company_id="COMP_A")
        self.assertEqual(len(hist1), 1)

        # Request 2: Uses Cache
        hist2 = get_history("EMP_001", "101", company_id="COMP_A")
        self.assertEqual(len(hist2), 1)
        self.assertEqual(mock_conn.execute.call_count, 2)  # DB was called only for request 1

    def test_13_pending_clarification_unaffected(self):
        """TEST 13 — PENDING CLARIFICATION: Memory hydration does not affect pending clarification."""
        set_pending_clarification("EMP_001", "101", {"original_question": "Show sales"})
        
        hist = get_history("EMP_001", "101")
        pending = get_pending_clarification("EMP_001", "101")
        
        self.assertIsNotNone(pending)
        self.assertEqual(pending["original_question"], "Show sales")
