"""Historical PE and PBV standard-deviation band analysis."""

import pandas as pd


def _safe_tz_strip(index):
    try:
        return index.tz_localize(None)
    except TypeError:
        return index.tz_convert(None)


def compute_valuation_bands(
    history: pd.DataFrame,
    quarterly_income: pd.DataFrame,
    quarterly_balance: pd.DataFrame,
    info: dict,
) -> dict:
    """Compute historical PE and PBV +/-1 SD / +/-2 SD valuation bands."""
    result = {"pe": None, "pbv": None}

    shares = (
        info.get("sharesOutstanding")
        or info.get("impliedSharesOutstanding")
        or info.get("floatShares")
    )

    close = history["Close"].copy()
    close.index = _safe_tz_strip(pd.to_datetime(close.index))

    # ── PE Bands ──────────────────────────────────────────────────────────────
    if not quarterly_income.empty and shares:
        try:
            ni_row = None
            for candidate in [
                "Net Income",
                "Net Income From Continuing Operations",
                "NetIncome",
                "Net Income Common Stockholders",
            ]:
                if candidate in quarterly_income.index:
                    ni_row = quarterly_income.loc[candidate]
                    break
            if ni_row is not None:
                ni = ni_row.sort_index()
                ni.index = _safe_tz_strip(pd.to_datetime(ni.index))
                t12_ni = ni.rolling(4, min_periods=4).sum()
                eps_series = (t12_ni / shares).dropna()
                if not eps_series.empty:
                    combined = close.to_frame("Close").join(
                        eps_series.rename("EPS"), how="left"
                    )
                    combined["EPS"] = combined["EPS"].ffill()
                    combined = combined.dropna()
                    if not combined.empty:
                        hist_pe = combined["Close"] / combined["EPS"]
                        hist_pe = hist_pe[hist_pe > 0]
                        if len(hist_pe) >= 8:
                            pe_mean = hist_pe.mean()
                            pe_std = hist_pe.std()
                            current_pe = hist_pe.iloc[-1]
                            sd_pos = (current_pe - pe_mean) / pe_std if pe_std > 0 else 0.0
                            eps_d = combined.loc[hist_pe.index, "EPS"]
                            result["pe"] = {
                                "dates":       hist_pe.index,
                                "close":       combined.loc[hist_pe.index, "Close"],
                                "band_m2":     eps_d * (pe_mean - 2 * pe_std),
                                "band_m1":     eps_d * (pe_mean - pe_std),
                                "band_mean":   eps_d * pe_mean,
                                "band_p1":     eps_d * (pe_mean + pe_std),
                                "band_p2":     eps_d * (pe_mean + 2 * pe_std),
                                "pe_mean":     round(pe_mean, 2),
                                "pe_std":      round(pe_std, 2),
                                "current_pe":  round(current_pe, 2),
                                "sd_position": round(sd_pos, 2),
                            }
        except Exception:
            pass

    # ── PBV Bands ─────────────────────────────────────────────────────────────
    if not quarterly_balance.empty and shares:
        try:
            eq_row = None
            for candidate in [
                "Stockholders Equity",
                "Common Stock Equity",
                "Total Equity Gross Minority Interest",
                "Total Stockholders Equity",
                "Total Equity",
            ]:
                if candidate in quarterly_balance.index:
                    eq_row = quarterly_balance.loc[candidate]
                    break
            if eq_row is not None:
                eq = eq_row.sort_index()
                eq.index = _safe_tz_strip(pd.to_datetime(eq.index))
                bvps = (eq / shares).dropna()
                if not bvps.empty:
                    combined_b = close.to_frame("Close").join(
                        bvps.rename("BVPS"), how="left"
                    )
                    combined_b["BVPS"] = combined_b["BVPS"].ffill()
                    combined_b = combined_b.dropna()
                    if not combined_b.empty:
                        hist_pbv = combined_b["Close"] / combined_b["BVPS"]
                        hist_pbv = hist_pbv[hist_pbv > 0]
                        if len(hist_pbv) >= 8:
                            pbv_mean = hist_pbv.mean()
                            pbv_std = hist_pbv.std()
                            current_pbv = hist_pbv.iloc[-1]
                            sd_pos_p = (current_pbv - pbv_mean) / pbv_std if pbv_std > 0 else 0.0
                            bvps_d = combined_b.loc[hist_pbv.index, "BVPS"]
                            result["pbv"] = {
                                "dates":        hist_pbv.index,
                                "close":        combined_b.loc[hist_pbv.index, "Close"],
                                "band_m2":      bvps_d * (pbv_mean - 2 * pbv_std),
                                "band_m1":      bvps_d * (pbv_mean - pbv_std),
                                "band_mean":    bvps_d * pbv_mean,
                                "band_p1":      bvps_d * (pbv_mean + pbv_std),
                                "band_p2":      bvps_d * (pbv_mean + 2 * pbv_std),
                                "pbv_mean":     round(pbv_mean, 2),
                                "pbv_std":      round(pbv_std, 2),
                                "current_pbv":  round(current_pbv, 2),
                                "sd_position":  round(sd_pos_p, 2),
                            }
        except Exception:
            pass

    return result
