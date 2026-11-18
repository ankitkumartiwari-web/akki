import unittest

from akki.facts import extract_incumbent, lookup_officeholder, parse_office_question


class OfficeholderTests(unittest.TestCase):
    def test_parse_question(self) -> None:
        self.assertEqual(
            parse_office_question("Who is the Vice President of India?"),
            ("vice president", "India"),
        )
        self.assertEqual(
            parse_office_question("Who is the current Prime Minister of India?"),
            ("prime minister", "India"),
        )
        self.assertEqual(
            parse_office_question("Who is the President of India now?"),
            ("president", "India"),
        )
        self.assertEqual(
            parse_office_question("Who is the PM of India?"),
            ("prime minister", "India"),
        )

    def test_parse_ignores_unrelated_questions(self) -> None:
        self.assertIsNone(parse_office_question("Explain the Two Sum problem"))

    def test_extract_incumbent(self) -> None:
        wikitext = (
            "| incumbent = [[C. P. Radhakrishnan]]\n"
            "| incumbent_since = 12 September 2025\n"
        )
        self.assertEqual(
            extract_incumbent(wikitext),
            ("C. P. Radhakrishnan", "12 September 2025"),
        )

    def test_lookup_officeholder(self) -> None:
        wikitext = (
            "| incumbent = [[Droupadi Murmu]]\n"
            "| incumbent_since = 25 July 2022\n"
        )
        answer = lookup_officeholder(
            "Who is the President of India?",
            fetch=lambda title: wikitext,
        )
        self.assertEqual(
            answer,
            "Droupadi Murmu is the president of India (since 25 July 2022).",
        )

    def test_lookup_falls_back_when_page_is_missing(self) -> None:
        self.assertIsNone(
            lookup_officeholder(
                "Who is the President of India?",
                fetch=lambda title: None,
            )
        )


if __name__ == "__main__":
    unittest.main()
