import io
import unittest
from unittest.mock import patch

from cma_curve.treasury import fetch_treasury_par
import main


class ProgressTests(unittest.TestCase):
    def test_treasury_reports_start_and_completion(self):
        xml = b'<feed><properties><NEW_DATE>2025-01-31</NEW_DATE><BC_10YEAR>4.5</BC_10YEAR></properties></feed>'
        messages = []
        def opener(url, timeout):
            self.assertEqual(timeout, 30)
            return io.BytesIO(xml)
        history, urls = fetch_treasury_par("2025-01-01", "2025-01-31",
                                          opener=opener, progress=messages.append)
        self.assertEqual(len(history), 1)
        self.assertEqual(len(urls), 1)
        self.assertIn("2025 (1/1)", messages[0])
        self.assertIn("received in", messages[1])

    def test_treasury_failure_identifies_year_and_preserves_cause(self):
        def opener(url, timeout):
            raise TimeoutError("timed out")
        with self.assertRaisesRegex(RuntimeError, "failed for 1996") as caught:
            fetch_treasury_par("1996-10-01", "2026-09-30", opener=opener)
        self.assertIsInstance(caught.exception.__cause__, TimeoutError)

    def test_all_tasks_share_bloomberg_client(self):
        with patch.object(main, "fetch_data") as fetch, patch.object(main, "BloombergClient") as factory:
            main.run(task="all")
        factory.assert_called_once_with("localhost", 8194)
        self.assertEqual(fetch.call_count, 5)
        for call in fetch.call_args_list:
            self.assertIs(call.kwargs["client"], factory.return_value)


if __name__ == "__main__":
    unittest.main()
