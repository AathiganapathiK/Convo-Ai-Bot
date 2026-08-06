import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import text

# Adjust path to resolve packages from backend directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.user_repository import UserRepository
from repositories.user_division_repository import UserDivisionRepository

class TestDivisionManagement(unittest.TestCase):
    def setUp(self):
        self.mock_connection = MagicMock()
        
    def test_user_repository_create_user(self):
        # Mock result of connection.execute for OUTPUT INSERTED.id
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        self.mock_connection.execute.return_value = mock_result
        
        user_data = {
            "username": "test@example.com",
            "password": "hashedpassword",
            "employee_id": "EMP1005",
            "full_name": "Test User",
            "official_email": "test@example.com",
            "department": "IT",
            "role": "USER",
            "company": "Ramraj Company",
            "company_id": "company-123"
        }
        
        user_id = UserRepository.create_user(user_data, self.mock_connection)
        
        self.assertEqual(user_id, 42)
        self.mock_connection.execute.assert_called_once()
        query_arg = self.mock_connection.execute.call_args[0][0]
        self.assertIn("OUTPUT INSERTED.id", query_arg.text)
        
    def test_user_repository_update_user(self):
        user_data = {
            "full_name": "Updated Name",
            "department": "HR",
            "role": "ADMIN",
            "company": "Ramraj Company",
            "company_id": "company-123",
            "location": "New Location",
            "mobile_number": "123456",
            "address": "New Address"
        }
        
        UserRepository.update_user(10, user_data, self.mock_connection)
        
        self.mock_connection.execute.assert_called_once()
        query_arg = self.mock_connection.execute.call_args[0][0]
        params_arg = self.mock_connection.execute.call_args[0][1]
        
        self.assertIn("UPDATE users", query_arg.text)
        self.assertEqual(params_arg["user_id"], 10)
        self.assertEqual(params_arg["full_name"], "Updated Name")
        
    @patch("repositories.user_division_repository.engine")
    def test_save_division_normalizes_empty_string(self, mock_engine):
        mock_conn = MagicMock()
        
        # Test empty string is normalized to None
        UserDivisionRepository.save_division(10, "", connection=mock_conn)
        
        mock_conn.execute.assert_called_once()
        params = mock_conn.execute.call_args[0][1]
        self.assertIsNone(params["division_code"])
        
    @patch("repositories.user_division_repository.engine")
    def test_save_division_preserves_valid_code(self, mock_engine):
        mock_conn = MagicMock()
        
        # Test valid division code is preserved
        UserDivisionRepository.save_division(10, "ACC", connection=mock_conn)
        
        mock_conn.execute.assert_called_once()
        params = mock_conn.execute.call_args[0][1]
        self.assertEqual(params["division_code"], "ACC")

if __name__ == "__main__":
    unittest.main()
