import unittest

import pandas as pd

from sensex_analysis import add_oi_analysis


class OIAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.chain = pd.DataFrame(
            {
                "Strike Price": [100, 110, 120, 130, 140, 150, 160],
                "Call Chng OI": [20, 1, 2, 3, 4, 5, -20],
                "Put Chng OI": [-10, 11, 12, 13, 14, 15, 40],
            }
        )

    def test_calculates_directional_three_strike_sums_and_boundaries(self):
        result = add_oi_analysis(self.chain)
        row = result.loc[result["Strike Price"] == 120].iloc[0]

        self.assertEqual(row["Call Sum"], 2 + 3 + 4)
        self.assertEqual(row["Put Sum"], 12 + 11 - 10)
        self.assertEqual(row["Difference"], -4)
        self.assertEqual(row["Call Boundary"], 4)
        self.assertEqual(row["Put Boundary"], 12)

    def test_flags_exits_and_far_otm_signals(self):
        result = add_oi_analysis(self.chain)
        row = result.loc[result["Strike Price"] == 120].iloc[0]

        self.assertEqual(row["Call ITM"], "Yes")
        self.assertEqual(row["Put ITM"], "Yes")
        self.assertEqual(row["Call Exits"], "No")
        self.assertEqual(row["Put Exits"], "No")
        self.assertEqual(result.iloc[0]["Put Exits"], "Yes")
        self.assertEqual(result.iloc[-1]["Call Exits"], "Yes")

    def test_missing_far_strikes_do_not_raise_or_create_itm_signals(self):
        result = add_oi_analysis(self.chain.iloc[:2])

        self.assertEqual(result["Call ITM"].tolist(), ["No"] * 2)
        self.assertEqual(result["Put ITM"].tolist(), ["No"] * 2)


if __name__ == "__main__":
    unittest.main()
