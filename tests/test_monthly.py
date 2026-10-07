import io
import unittest
import pandas as pd

from cma_curve.bloomberg import BloombergClient
from cma_curve.data import completed_month_end, monthly_sample
from cma_curve.treasury import fetch_treasury_par


class MonthlyTests(unittest.TestCase):
    def test_completed_month_end_including_leap_year(self):
        self.assertEqual(completed_month_end("2026-10-06"), pd.Timestamp("2026-09-30"))
        self.assertEqual(completed_month_end("2026-09-30"), pd.Timestamp("2026-09-30"))
        self.assertEqual(completed_month_end("2024-03-01"), pd.Timestamp("2024-02-29"))

    def test_month_end_preserves_dates_and_missing_months(self):
        history = pd.DataFrame({"date": pd.to_datetime(["2026-07-30", "2026-07-31", "2026-07-30", "2026-09-30", "2026-10-02"]),
                                "key": ["a", "a", "b", "a", "a"], "value": [1., 2., 3., 4., 5.]})
        result = monthly_sample(history, "2026-10-06")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[result.key.eq("b")].date.iloc[0], pd.Timestamp("2026-07-30"))
        self.assertEqual(set(result.month), {"2026-07", "2026-09"})
        self.assertEqual(result[(result.key == "a") & (result.month == "2026-07")].value.iloc[0], 2.)

    def test_bloomberg_requests_calendar_monthly_periodicity(self):
        class Backend:
            def bdh(self, **kwargs):
                self.kwargs = kwargs
                return pd.DataFrame(columns=["date", "ticker", "field", "value"])
        backend = Backend()
        BloombergClient(backend=backend).history(["A"], ["PX_LAST"], "1986-10-01", "2026-09-30", frequency="monthly")
        self.assertEqual(backend.kwargs["Per"], "M")
        self.assertEqual(backend.kwargs["periodicityAdjustment"], "CALENDAR")

    def test_treasury_clamps_early_start_and_reports_it(self):
        xml = b'<feed xmlns:m="urn:m" xmlns:d="urn:d"><m:properties><d:NEW_DATE>1990-01-31T00:00:00</d:NEW_DATE><d:BC_10YEAR>8.5</d:BC_10YEAR></m:properties></feed>'
        urls = []
        def opener(url, timeout):
            urls.append(url)
            return io.BytesIO(xml)
        with self.assertWarnsRegex(UserWarning, "starts in 1990"):
            history, _ = fetch_treasury_par("1986-10-01", "1990-01-31", opener=opener)
        self.assertEqual(len(urls), 1)
        self.assertIn("=1990", urls[0])
        self.assertEqual(history.date.min(), pd.Timestamp("1990-01-31"))

    def test_defaults_cover_thirty_complete_years(self):
        import main
        self.assertEqual(main.FREQUENCY, "monthly")
        self.assertEqual(len(pd.period_range(main.START_DATE, main.END_DATE, freq="M")), 360)


if __name__ == "__main__":
    unittest.main()
