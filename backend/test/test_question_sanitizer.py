import unittest
from semantic.matching.question_sanitizer import QuestionSanitizer

class TestQuestionSanitizer(unittest.TestCase):

    def test_case_1_plain_question(self):
        # Test 1: Input "Show banian sales" -> Output "Show banian sales"
        input_text = "Show banian sales"
        expected = "Show banian sales"
        self.assertEqual(QuestionSanitizer.sanitize(input_text), expected)

    def test_case_2_original_and_followup(self):
        # Test 2: Input with Original Question and Follow-up Question
        input_text = """
        Original Question:
        Show banian sales

        Follow-up Question:
        Quarterly trend
        """
        expected = "Show banian sales"
        self.assertEqual(QuestionSanitizer.sanitize(input_text), expected)

    def test_case_3_question_label(self):
        # Test 3: Input "Question:\nShow cotton shirt sales" -> Output "Show cotton shirt sales"
        input_text = """
        Question:
        Show cotton shirt sales
        """
        expected = "Show cotton shirt sales"
        self.assertEqual(QuestionSanitizer.sanitize(input_text), expected)

    def test_case_4_context_then_question(self):
        # Test 4: Input with Context then Question -> Output "Banian"
        input_text = """
        Context:
        Monthly report

        Question:
        Banian
        """
        expected = "Banian"
        self.assertEqual(QuestionSanitizer.sanitize(input_text), expected)

    def test_case_5_extra_spaces(self):
        # Test 5: Extra spaces collapsing -> Output "Banian"
        input_text = """
        Question:


        Banian
        """
        expected = "Banian"
        self.assertEqual(QuestionSanitizer.sanitize(input_text), expected)

    def test_empty_input(self):
        self.assertEqual(QuestionSanitizer.sanitize(""), "")
        self.assertEqual(QuestionSanitizer.sanitize(None), "")

if __name__ == "__main__":
    unittest.main()
