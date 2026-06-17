"""
excel_writer.py
---------------
Enhanced Excel Report Generator

Sheet structure:
  Sheet 1: "Top Selected Sectors"  — Justifications, oversold highlights, rejected sectors
  Sheet 2: "Union of Stocks"       — All stocks from selected indices with all metrics + flags
  Sheet 3: "Top Rebound Picks"     — Stocks with Rebound Score > 70 & action BUY/WAIT
  Sheet 4: "Final Recommendations" — Original algo output (all stocks)
  Sheet 5: "Top Picks"             — Original top BUY stocks
  Sheet 6: "Top Sells"             — Original top SELL stocks
  Sheet 7: "Layer 1 - Fundamentals"
  Sheet 8: "Layer 2 - Technicals"
  Sheet 9: "Layer 3 - Statistical"
"""

import os
import sys
from datetime import datetime

import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class ExcelWriter:
    def __init__(self, config: dict):
        self.config = config

    # ------------------------------------------------------------------
    # Original save_report (kept intact for backward compatibility)
    # ------------------------------------------------------------------

    def save_report(self, df_final: pd.DataFrame, index_name: str = "Nifty 500",
                    subfolder: str = None) -> str:
        timestamp        = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        clean_index_name = index_name.replace(' ', '_')
        filename         = f"{clean_index_name}_Deep_Analysis_{timestamp}.xlsx"

        folder = self.config['paths']['output_folder']
        if subfolder:
            folder = os.path.join(folder, subfolder)
        path = os.path.join(folder, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        top_picks = df_final[df_final['Action'] == 'BUY'].sort_values(
            by=['Score', 'Confidence'], ascending=False).head(20)
        top_sells = df_final[df_final['Action'] == 'SELL'].sort_values(
            by=['Score', 'Confidence'], ascending=[True, False]).head(20)

        l1_cols      = ['Symbol', 'Action', 'L1_Score', 'L1_Reasoning', 'MarketCap_Cr']
        l2_cols      = ['Symbol', 'Action', 'L2_Score', 'L2_Reasoning', 'Price']
        l3_cols      = ['Symbol', 'Action', 'L3_Score', 'L3_Reasoning', 'P_Target', 'P_Stop', 'Pred_Return']
        summary_cols = ['Symbol', 'Action', 'Score', 'Confidence', 'Horizon', 'Price']

        with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
            df_final[summary_cols].to_excel(writer, sheet_name='Final Recommendations', index=False)
            top_picks[summary_cols].to_excel(writer, sheet_name='Top Picks', index=False)
            top_sells[summary_cols].to_excel(writer, sheet_name='Top Sells', index=False)
            df_final[l1_cols].to_excel(writer, sheet_name='Layer 1 - Fundamentals', index=False)
            df_final[l2_cols].to_excel(writer, sheet_name='Layer 2 - Technicals', index=False)
            df_final[l3_cols].to_excel(writer, sheet_name='Layer 3 - Statistical', index=False)
            self._apply_formatting(writer)

        print(f"Deep Analysis Report saved to {path}")
        return path

    # ------------------------------------------------------------------
    # Consolidated report — new main entry point
    # ------------------------------------------------------------------

    def save_consolidated_report(
        self,
        df_union:            pd.DataFrame,
        selected_indices:    list,
        justifications:      dict,
        oversold_highlights: dict,
        rejected_sectors:    list,
        all_scores:          dict,
        vix:                 float,
        subfolder:           str = None,
    ) -> str:
        """
        Generate the full consolidated Excel report.

        Sheet 1:  Top Selected Sectors (justifications + oversold highlights)
        Sheet 2:  Union of Stocks (all metrics, flags, rebound scores)
        Sheet 3:  Top Rebound Picks (Rebound Score > 70)
        Sheet 4+: Original algorithm sheets (Final Recommendations, Top Picks, etc.)
        """
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        filename  = f"Sector_Select_Consolidated_{timestamp}.xlsx"

        folder = self.config['paths']['output_folder']
        if subfolder:
            folder = os.path.join(folder, subfolder)
        path = os.path.join(folder, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
            workbook = writer.book

            # ── Define formats ─────────────────────────────────────────
            fmt_title = workbook.add_format({
                'bold': True, 'font_size': 14, 'font_color': '#FFFFFF',
                'bg_color': '#1F3864', 'border': 1, 'text_wrap': True
            })
            fmt_header = workbook.add_format({
                'bold': True, 'font_size': 10, 'font_color': '#FFFFFF',
                'bg_color': '#1F4E78', 'border': 1, 'text_wrap': True, 'align': 'center'
            })
            fmt_header_green = workbook.add_format({
                'bold': True, 'font_size': 10, 'font_color': '#FFFFFF',
                'bg_color': '#1E6B3C', 'border': 1, 'text_wrap': True, 'align': 'center'
            })
            fmt_body = workbook.add_format({
                'font_size': 10, 'border': 1, 'text_wrap': True, 'valign': 'top'
            })
            fmt_body_num = workbook.add_format({
                'font_size': 10, 'border': 1, 'num_format': '#,##0.00', 'align': 'center'
            })
            fmt_flag_yes = workbook.add_format({
                'font_size': 10, 'border': 1, 'bold': True,
                'font_color': '#FFFFFF', 'bg_color': '#C00000', 'align': 'center'
            })
            fmt_flag_no = workbook.add_format({
                'font_size': 10, 'border': 1, 'align': 'center', 'font_color': '#595959'
            })
            fmt_sector_title = workbook.add_format({
                'bold': True, 'font_size': 12, 'font_color': '#FFFFFF',
                'bg_color': '#2E75B6', 'border': 1
            })
            fmt_justification = workbook.add_format({
                'font_size': 9, 'text_wrap': True, 'valign': 'top',
                'bg_color': '#EBF3FB', 'border': 1
            })
            fmt_highlight_hdr = workbook.add_format({
                'bold': True, 'font_size': 9, 'bg_color': '#D6E4F0', 'border': 1, 'align': 'center'
            })
            fmt_rejected = workbook.add_format({
                'font_size': 9, 'text_wrap': True, 'font_color': '#7F7F7F',
                'bg_color': '#F2F2F2', 'border': 1, 'italic': True
            })
            fmt_score_high = workbook.add_format({
                'font_size': 10, 'border': 1, 'bold': True,
                'font_color': '#FFFFFF', 'bg_color': '#375623', 'align': 'center'
            })
            fmt_score_mid = workbook.add_format({
                'font_size': 10, 'border': 1,
                'font_color': '#375623', 'bg_color': '#E2EFDA', 'align': 'center'
            })
            fmt_score_low = workbook.add_format({
                'font_size': 10, 'border': 1,
                'font_color': '#843C0C', 'bg_color': '#FCE4D6', 'align': 'center'
            })
            fmt_date = workbook.add_format({
                'bold': True, 'font_size': 9, 'font_color': '#595959', 'border': 0
            })
            fmt_vix_warn = workbook.add_format({
                'bold': True, 'font_size': 10, 'font_color': '#FFFFFF',
                'bg_color': '#C55A11', 'border': 1, 'align': 'center'
            })

            formats = {
                'title': fmt_title, 'header': fmt_header, 'header_green': fmt_header_green,
                'body': fmt_body, 'body_num': fmt_body_num,
                'flag_yes': fmt_flag_yes, 'flag_no': fmt_flag_no,
                'sector_title': fmt_sector_title, 'justification': fmt_justification,
                'highlight_hdr': fmt_highlight_hdr, 'rejected': fmt_rejected,
                'score_high': fmt_score_high, 'score_mid': fmt_score_mid, 'score_low': fmt_score_low,
                'date': fmt_date, 'vix_warn': fmt_vix_warn,
            }

            # ── Sheet 1: Top Selected Sectors ──────────────────────────
            self._write_sector_sheet(
                writer, workbook, formats,
                selected_indices, justifications, oversold_highlights,
                rejected_sectors, all_scores, vix
            )

            # ── Sheet 2: Union of Stocks ───────────────────────────────
            self._write_union_sheet(writer, workbook, formats, df_union)

            # ── Sheet 3: Top Rebound Picks ─────────────────────────────
            self._write_rebound_picks_sheet(writer, workbook, formats, df_union)

            # ── Sheets 4–9: Original Algorithm Sheets ──────────────────
            self._write_original_sheets(writer, workbook, formats, df_union)

        print(f"\n[SAVED] Consolidated Report saved to:\n   {path}")
        return path

    # ------------------------------------------------------------------
    # Sheet 1: Top Selected Sectors
    # ------------------------------------------------------------------

    def _write_sector_sheet(self, writer, workbook, formats,
                             selected_indices, justifications, oversold_highlights,
                             rejected_sectors, all_scores, vix):
        ws = workbook.add_worksheet("Top Selected Sectors")
        writer.sheets["Top Selected Sectors"] = ws

        ws.set_column('A:A', 28)
        ws.set_column('B:B', 90)
        ws.set_column('C:M', 15)

        row = 0

        # Title
        ws.merge_range(row, 0, row, 9,
            f"Pre-Layer Sector Selection Report | Generated: {datetime.now().strftime('%d %b %Y %H:%M')}  |  India VIX: {vix:.2f}",
            formats['title'])
        row += 1

        if vix > 20:
            ws.merge_range(row, 0, row, 9,
                f"VIX ALERT: India VIX = {vix:.1f} exceeds 20. "
                "Defensive sector rule applied -- least volatile defensive included. "
                "Sectors with '*** DEFENSIVE ***' tag are risk-management additions.",
                formats['vix_warn'])
            row += 1

        row += 1

        # ── Section: Selected Sectors Summary Table ──────────────────
        ws.merge_range(row, 0, row, 9, ">> TOP SELECTED SECTORS", formats['sector_title'])
        row += 1

        hdr_cols = ["Rank", "Index Name", "Composite Score", "Factor A\n(Econ Phase)",
                    "Factor B\n(Seasonality)", "Factor C\n(Technical)", "Factor D\n(Fundamentals)",
                    "Factor E\n(Policy)", "RSI", "% from 52W High"]
        for c, h in enumerate(hdr_cols):
            ws.write(row, c, h, formats['header'])
        row += 1

        for rank_num, idx in enumerate(selected_indices, 1):
            sc   = all_scores.get(idx, {})
            comp = sc.get('composite', 0)
            ws.write(row, 0, rank_num,                formats['body_num'])
            ws.write(row, 1, idx,                     formats['body'])
            ws.write(row, 2, round(comp, 1),          formats['score_high'] if comp >= 70 else
                                                       formats['score_mid']  if comp >= 55 else
                                                       formats['score_low'])
            ws.write(row, 3, round(sc.get('score_A', 0), 1), formats['body_num'])
            ws.write(row, 4, round(sc.get('score_B', 0), 1), formats['body_num'])
            ws.write(row, 5, round(sc.get('score_C', 0), 1), formats['body_num'])
            ws.write(row, 6, round(sc.get('score_D', 0), 1), formats['body_num'])
            ws.write(row, 7, round(sc.get('score_E', 0), 1), formats['body_num'])
            ws.write(row, 8, "—", formats['body'])   # RSI from tech data
            ws.write(row, 9, "—", formats['body'])   # % from high
            row += 1

        row += 2

        # ── Section: Detailed Justifications ─────────────────────────
        ws.merge_range(row, 0, row, 9, ">> DETAILED SECTOR JUSTIFICATIONS", formats['sector_title'])
        row += 1

        for rank_num, idx in enumerate(selected_indices, 1):
            # Sector header
            ws.merge_range(row, 0, row, 9,
                f"  {rank_num}. {idx}  (Composite Score: {all_scores.get(idx, {}).get('composite', 0):.1f} / 100)",
                formats['sector_title'])
            row += 1

            # Justification text
            jtext = justifications.get(idx, "")
            ws.merge_range(row, 0, row + 14, 9, jtext, formats['justification'])
            row += 15

            # Oversold Stock Highlights
            highlights = oversold_highlights.get(idx, [])
            if highlights:
                ws.merge_range(row, 0, row, 9,
                    f"  Top Oversold Stocks in {idx}:", formats['highlight_hdr'])
                row += 1

                h_hdr = ["Symbol", "Rebound Score", "Current Price", "52W High", "52W Low",
                         "% from 52W High", "% above 52W Low", "RSI", "P/E", "ROE %",
                         "Revenue Growth %", "OVERSOLD Flag", "52W_LOW Flag"]
                for c, h in enumerate(h_hdr):
                    ws.write(row, c, h, formats['highlight_hdr'])
                row += 1

                for h in highlights:
                    ws.write(row, 0,  h.get('symbol', ''),                              formats['body'])
                    ws.write(row, 1,  h.get('rebound_score', 0),                         formats['score_high'] if h.get('rebound_score', 0) >= 70 else formats['score_mid'])
                    ws.write(row, 2,  round(h.get('current_price', 0), 2),              formats['body_num'])
                    ws.write(row, 3,  round(h.get('high_52w', 0), 2),                   formats['body_num'])
                    ws.write(row, 4,  round(h.get('low_52w', 0), 2),                    formats['body_num'])
                    ws.write(row, 5,  round(h.get('pct_from_52w_high', 0), 1),          formats['body_num'])
                    ws.write(row, 6,  round(h.get('pct_from_52w_low', 0), 1),           formats['body_num'])
                    ws.write(row, 7,  round(h.get('rsi_latest', 0), 1),                 formats['body_num'])
                    pe_val = h.get('pe')
                    ws.write(row, 8,  round(pe_val, 1) if pe_val else "N/A",            formats['body_num'] if pe_val else formats['body'])
                    ws.write(row, 9,  round(h.get('roe', 0), 1),                        formats['body_num'])
                    ws.write(row, 10, round(h.get('rev_growth', 0), 1),                 formats['body_num'])
                    flag_os = h.get('flag_oversold', 'NO')
                    flag_52 = h.get('flag_52w_low', 'NO')
                    ws.write(row, 11, flag_os, formats['flag_yes'] if flag_os == 'YES' else formats['flag_no'])
                    ws.write(row, 12, flag_52, formats['flag_yes'] if flag_52 == 'YES' else formats['flag_no'])
                    row += 1

            row += 2

        # ── Section: Rejected Sectors ─────────────────────────────────
        if rejected_sectors:
            ws.merge_range(row, 0, row, 9, ">> SECTORS REVIEWED BUT NOT SELECTED", formats['sector_title'])
            row += 1
            ws.write(row, 0, "Index Name",  formats['header'])
            ws.write(row, 1, "Reason for Rejection / Lower Priority", formats['header'])
            row += 1
            for idx_r, reason in rejected_sectors:
                ws.write(row, 0, idx_r,  formats['body'])
                ws.write(row, 1, reason, formats['rejected'])
                row += 1

        ws.freeze_panes(1, 0)

    # ------------------------------------------------------------------
    # Sheet 2: Union of Stocks
    # ------------------------------------------------------------------

    def _write_union_sheet(self, writer, workbook, formats, df_union: pd.DataFrame):
        # Column ordering for the union sheet
        union_cols = [
            'Symbol', 'Index_Name', 'Price', 'Action',
            'Final_Rank_Score', 'Rebound_Score', 'Score',
            'Flag_52W_LOW', 'Flag_OVERSOLD', 'Flag_Double_Bottom', 'Double_Bottom_Stage', 'Double_Bottom_Score',
            '52W_High', '52W_Low', 'Pct_From_52W_High', 'Pct_From_52W_Low',
            'RSI', 'PE_Ratio', 'PB_Ratio', 'ROE', 'Revenue_Growth_Pct', 'Debt_Equity',
            'Oversold_Score', 'Valuation_Score', 'Growth_Score', 'Technical_Score', 'Momentum_Score',
            'Confidence', 'Horizon', 'MarketCap_Cr',
            'L1_Score', 'L2_Score', 'L3_Score',
            'P_Target', 'P_Stop', 'Pred_Return',
        ]
        # Only include columns that exist
        union_cols = [c for c in union_cols if c in df_union.columns]

        df_out = df_union[union_cols].copy()
        df_out = df_out.sort_values('Final_Rank_Score', ascending=False).reset_index(drop=True)

        df_out.to_excel(writer, sheet_name='Union of Stocks', index=True, startrow=1)

        ws = writer.sheets['Union of Stocks']
        ws.set_row(0, 20)
        ws.merge_range(0, 0, 0, len(union_cols),
            "Union of Stocks from Selected Indices  |  Sorted by Final Rank Score (70% Algo + 30% Rebound)",
            formats['title'])

        ws.set_column('A:A', 6)   # index
        ws.set_column('B:B', 14)  # Symbol
        ws.set_column('C:C', 30)  # Index_Name
        ws.set_column('D:D', 9)   # Price
        ws.set_column('E:E', 10)  # Action
        ws.set_column('F:F', 14)  # Final_Rank_Score
        ws.set_column('G:G', 13)  # Rebound_Score
        ws.set_column('H:H', 10)  # Score
        ws.set_column('I:L', 12)  # Flags
        ws.set_column('M:AG', 14) # Rest

        ws.freeze_panes(2, 2)

        # Apply conditional formatting for flags
        flag_os_col = union_cols.index('Flag_OVERSOLD') + 2 if 'Flag_OVERSOLD' in union_cols else None
        flag_52_col = union_cols.index('Flag_52W_LOW')  + 2 if 'Flag_52W_LOW'  in union_cols else None
        flag_db_col = union_cols.index('Flag_Double_Bottom') + 2 if 'Flag_Double_Bottom' in union_cols else None

        n_rows = len(df_out)
        if flag_os_col:
            ws.conditional_format(2, flag_os_col, n_rows + 1, flag_os_col, {
                'type': 'cell', 'criteria': '==', 'value': '"YES"',
                'format': workbook.add_format({'bg_color': '#C00000', 'font_color': 'white', 'bold': True})
            })
        if flag_52_col:
            ws.conditional_format(2, flag_52_col, n_rows + 1, flag_52_col, {
                'type': 'cell', 'criteria': '==', 'value': '"YES"',
                'format': workbook.add_format({'bg_color': '#ED7D31', 'font_color': 'white', 'bold': True})
            })
        if flag_db_col:
            ws.conditional_format(2, flag_db_col, n_rows + 1, flag_db_col, {
                'type': 'cell', 'criteria': '==', 'value': '"YES"',
                'format': workbook.add_format({'bg_color': '#7030A0', 'font_color': 'white', 'bold': True})
            })

        # Conditional format for Rebound Score
        rs_col = union_cols.index('Rebound_Score') + 2 if 'Rebound_Score' in union_cols else None
        if rs_col:
            ws.conditional_format(2, rs_col, n_rows + 1, rs_col, {
                'type': '3_color_scale',
                'min_color': '#FCE4D6', 'mid_color': '#FFEB9C', 'max_color': '#E2EFDA'
            })

    # ------------------------------------------------------------------
    # Sheet 3: Top Rebound Picks
    # ------------------------------------------------------------------

    def _write_rebound_picks_sheet(self, writer, workbook, formats, df_union: pd.DataFrame):
        mask = (df_union['Rebound_Score'] >= 70) | (df_union['Flag_OVERSOLD'] == 'YES')
        df_rb = df_union[mask].sort_values('Rebound_Score', ascending=False).head(50)

        if df_rb.empty:
            df_rb = df_union.sort_values('Rebound_Score', ascending=False).head(20)

        rb_cols = [
            'Symbol', 'Index_Name', 'Price', 'Action', 'Final_Rank_Score',
            'Rebound_Score', 'Flag_52W_LOW', 'Flag_OVERSOLD', 'Flag_Double_Bottom', 'Double_Bottom_Stage',
            'Pct_From_52W_High', 'Pct_From_52W_Low', 'RSI',
            'PE_Ratio', 'ROE', 'Revenue_Growth_Pct', 'Score', 'Confidence'
        ]
        rb_cols = [c for c in rb_cols if c in df_rb.columns]
        df_rb[rb_cols].to_excel(writer, sheet_name='Top Rebound Picks', index=False, startrow=1)

        ws = writer.sheets['Top Rebound Picks']
        ws.merge_range(0, 0, 0, len(rb_cols) - 1,
            "Top Rebound Picks -- Stocks with Rebound Score >= 70 OR OVERSOLD Flag (Highest Upside Potential)",
            formats['title'])
        ws.set_column('A:A', 14)
        ws.set_column('B:B', 28)
        ws.set_column('C:P', 15)
        ws.freeze_panes(2, 2)

        n_rows = len(df_rb)
        rs_col = rb_cols.index('Rebound_Score') if 'Rebound_Score' in rb_cols else None
        if rs_col is not None:
            ws.conditional_format(2, rs_col, n_rows + 1, rs_col, {
                'type': '3_color_scale',
                'min_color': '#FCE4D6', 'mid_color': '#FFEB9C', 'max_color': '#375623'
            })

    # ------------------------------------------------------------------
    # Sheets 4–9: Original algorithm sheets (preserved unchanged)
    # ------------------------------------------------------------------

    def _write_original_sheets(self, writer, workbook, formats, df_union: pd.DataFrame):
        summary_cols = ['Symbol', 'Index_Name', 'Action', 'Score', 'Confidence', 'Horizon', 'Price']
        summary_cols = [c for c in summary_cols if c in df_union.columns]

        l1_cols = ['Symbol', 'Index_Name', 'Action', 'L1_Score', 'L1_Reasoning', 'MarketCap_Cr']
        l2_cols = ['Symbol', 'Index_Name', 'Action', 'L2_Score', 'L2_Reasoning', 'Price']
        l3_cols = ['Symbol', 'Index_Name', 'Action', 'L3_Score', 'L3_Reasoning', 'P_Target', 'P_Stop', 'Pred_Return']

        for col_list in [l1_cols, l2_cols, l3_cols, summary_cols]:
            col_list[:] = [c for c in col_list if c in df_union.columns]

        top_picks = df_union[df_union['Action'] == 'BUY'].sort_values(
            by=['Score', 'Confidence'], ascending=False).head(20)
        top_sells = df_union[df_union['Action'] == 'SELL'].sort_values(
            by=['Score', 'Confidence'], ascending=[True, False]).head(20)

        sheets_data = [
            ('Final Recommendations', df_union[summary_cols]),
            ('Top Picks',             top_picks[summary_cols] if not top_picks.empty else df_union[summary_cols].head(0)),
            ('Top Sells',             top_sells[summary_cols] if not top_sells.empty else df_union[summary_cols].head(0)),
            ('Layer 1 - Fundamentals', df_union[l1_cols]),
            ('Layer 2 - Technicals',   df_union[l2_cols]),
            ('Layer 3 - Statistical',  df_union[l3_cols]),
        ]

        for sheet_name, df_sheet in sheets_data:
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            ws.freeze_panes(1, 0)
            ws.set_column('A:Z', 15)
            if 'Reasoning' in sheet_name or 'Layer' in sheet_name:
                ws.set_column('E:E', 80)
            # Write header row with formatting
            for col_num, col_name in enumerate(df_sheet.columns):
                ws.write(0, col_num, col_name, formats['header'])

    # ------------------------------------------------------------------
    # Generic formatting helper
    # ------------------------------------------------------------------

    def _apply_formatting(self, writer):
        workbook    = writer.book
        header_fmt  = workbook.add_format({
            'bold': True, 'bg_color': '#1F4E78', 'font_color': 'white', 'border': 1
        })
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            ws.freeze_panes(1, 0)
            ws.set_column('A:Z', 15)
            ws.set_column('D:D', 40)
            if sheet_name.startswith('Layer'):
                ws.set_column('D:D', 80)
