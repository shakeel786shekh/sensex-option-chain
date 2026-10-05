"""Open-interest analytics for the SENSEX option chain."""

import pandas as pd


ANALYSIS_HEADERS = [
    "Call Sum",
    "Put Sum",
    "Difference",
    "Call Boundary",
    "Put Boundary",
    "Call Exits",
    "Put Exits",
    "Call ITM",
    "Put ITM",
]


def add_oi_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Add directional open-interest signals to a strike-sorted option chain."""
    result = df.sort_values("Strike Price").reset_index(drop=True).copy()
    call_change = pd.to_numeric(result["Call Chng OI"], errors="coerce").fillna(0)
    put_change = pd.to_numeric(result["Put Chng OI"], errors="coerce").fillna(0)

    result["Call Sum"] = (
        call_change
        + call_change.shift(-1, fill_value=0)
        + call_change.shift(-2, fill_value=0)
    )
    result["Put Sum"] = (
        put_change
        + put_change.shift(1, fill_value=0)
        + put_change.shift(2, fill_value=0)
    )
    result["Difference"] = result["Call Sum"] - result["Put Sum"]
    result["Call Boundary"] = call_change.shift(-2, fill_value=0)
    result["Put Boundary"] = put_change
    result["Call Exits"] = (
        (result["Call Sum"] < 0) | (result["Call Boundary"] < 0)
    ).map({True: "Yes", False: "No"})
    result["Put Exits"] = (
        (result["Put Sum"] < 0) | (result["Put Boundary"] < 0)
    ).map({True: "Yes", False: "No"})

    call_itm = []
    put_itm = []
    for index in range(len(result)):
        call_target = index + 4
        if call_target < len(result):
            far_call_change = call_change.iloc[call_target]
            far_put_change = put_change.iloc[call_target]
            call_itm.append(
                "Yes"
                if far_call_change < 0
                and far_put_change > 0
                and abs(far_put_change / far_call_change) > 1.5
                else "No"
            )
        else:
            call_itm.append("No")

        put_target = index - 2
        if put_target >= 0:
            far_put_change = put_change.iloc[put_target]
            far_call_change = call_change.iloc[put_target]
            put_itm.append(
                "Yes"
                if far_put_change < 0
                and far_call_change > 0
                and abs(far_call_change / far_put_change) > 1.5
                else "No"
            )
        else:
            put_itm.append("No")

    result["Call ITM"] = call_itm
    result["Put ITM"] = put_itm
    return result
