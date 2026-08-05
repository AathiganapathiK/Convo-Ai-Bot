import unittest
from semantic.matching.candidate_phrase_extractor import CandidatePhraseExtractor

class TestCandidatePhraseExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = CandidatePhraseExtractor()

    def test_single_value_with_stopwords(self):
        # Test 1
        res = self.extractor.extract("Show Banian sales")
        self.assertEqual(res, ["banian"])

    def test_two_words_with_stopwords(self):
        # Test 2
        res = self.extractor.extract("Show Cotton Shirt sales")
        self.assertEqual(res, ["cotton shirt", "cotton", "shirt"])

    def test_three_words_with_stopwords(self):
        # Test 3
        res = self.extractor.extract("Show Black Formal Shirt sales")
        self.assertEqual(res, [
            "black formal shirt",
            "black formal",
            "formal shirt",
            "black",
            "formal",
            "shirt"
        ])

    def test_irregular_case_with_stopwords(self):
        # Test 4
        res = self.extractor.extract("Give Mens Wear revenue")
        self.assertEqual(res, ["mens wear", "mens", "wear"])

    def test_preposition_with_stopwords(self):
        # Test 5
        res = self.extractor.extract("Show sales in South Region")
        self.assertEqual(res, ["south region", "south", "region"])

    def test_only_stopwords(self):
        # Test 6
        res = self.extractor.extract("Show sales")
        self.assertEqual(res, [])

if __name__ == "__main__":
    unittest.main()
