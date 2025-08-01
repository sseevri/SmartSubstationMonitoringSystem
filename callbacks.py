from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
from dash import html
from datetime import datetime, timedelta
import pandas as pd

def register_callbacks(app, load_latest_csv_data, METER_NAMES, audit_logger, RYB_COLORS):
    for meter_id in METER_NAMES.keys():
        @app.callback(
            [Output(f'meter-{meter_id}-status', 'children'),
             Output(f'meter-{meter_id}-vry', 'children'),
             Output(f'meter-{meter_id}-vyb', 'children'),
             Output(f'meter-{meter_id}-vbr', 'children'),
             Output(f'meter-{meter_id}-vll', 'children'),
             Output(f'meter-{meter_id}-vr', 'children'),
             Output(f'meter-{meter_id}-vy', 'children'),
             Output(f'meter-{meter_id}-vb', 'children'),
             Output(f'meter-{meter_id}-vln', 'children'),
             Output(f'meter-{meter_id}-cr', 'children'),
             Output(f'meter-{meter_id}-cy', 'children'),
             Output(f'meter-{meter_id}-cb', 'children'),
             Output(f'meter-{meter_id}-ct', 'children'),
             Output(f'meter-{meter_id}-wr', 'children'),
             Output(f'meter-{meter_id}-wy', 'children'),
             Output(f'meter-{meter_id}-wb', 'children'),
             Output(f'meter-{meter_id}-wt', 'children'),
             Output(f'meter-{meter_id}-pfr', 'children'),
             Output(f'meter-{meter_id}-pfy', 'children'),
             Output(f'meter-{meter_id}-pfb', 'children'),
             Output(f'meter-{meter_id}-pfa', 'children'),
             Output(f'meter-{meter_id}-wh', 'children'),
             Output(f'meter-{meter_id}-vah', 'children'),
             Output(f'meter-{meter_id}-varhi', 'children'),
             Output(f'meter-{meter_id}-varhc', 'children')],
            Input(f'interval-meter-{meter_id}', 'n_intervals')
        )
        def update_meter_data(n, current_meter_id=meter_id):
            try:
                df, error_message = load_latest_csv_data()
                if error_message:
                    return (html.Div(error_message),) + ("0.00",) * 23
                if df.empty:
                    audit_logger.warning(f"No CSV data available for meter {current_meter_id} page update")
                    return (html.Div(),) + ("0.00",) * 23

                meter_df = df[df['Meter_ID'] == current_meter_id].tail(1).reset_index()
                if meter_df.empty:
                    audit_logger.warning(f"No data available for Meter ID {current_meter_id} after filtering")
                    return (html.Div(),) + ("0.00",) * 23

                status = "Communication Failed"
                if 'comm_status' in meter_df.columns and 'status' in meter_df.columns:
                    status = "Communication Failed" if meter_df.iloc[0]['comm_status'] == "FAILED" else meter_df.iloc[0]['status']
                else:
                    audit_logger.warning(f"Missing 'comm_status' or 'status' columns for meter {current_meter_id}")

                is_stale = (datetime.now() - pd.to_datetime(meter_df.iloc[0]['DateTime'])).total_seconds() > 120

                if is_stale:
                    status_color = "orange"
                    status = "Stale"
                elif status in ['EB supply On', 'DG set On', 'OK']:
                    status_color = 'green'
                elif status in ['EB supply Off', 'DG set Off', 'POWER_FAIL']:
                    status_color = 'yellow'
                else:
                    status_color = 'red'
                status_alert = html.Div(
                    dbc.Alert(status, color=RYB_COLORS[status_color], className="fade show"),
                    className="text-center"
                ) if status != "OK" else html.Div()

                # Parameter values with fallback for missing columns
                vry = meter_df['Vry Phase'].iloc[0] if 'Vry Phase' in meter_df.columns else 0.00
                vyb = meter_df['Vyb Phase'].iloc[0] if 'Vyb Phase' in meter_df.columns else 0.00
                vbr = meter_df['Vbr Phase'].iloc[0] if 'Vbr Phase' in meter_df.columns else 0.00
                vll = meter_df['VLL Average'].iloc[0] if 'VLL Average' in meter_df.columns else 0.00
                vr = meter_df['V R phase'].iloc[0] if 'V R phase' in meter_df.columns else 0.00
                vy = meter_df['V Y phase'].iloc[0] if 'V Y phase' in meter_df.columns else 0.00
                vb = meter_df['V B phase'].iloc[0] if 'V B phase' in meter_df.columns else 0.00
                vln = meter_df['VLN Average'].iloc[0] if 'VLN Average' in meter_df.columns else 0.00
                cr = meter_df['Current R phase'].iloc[0] if 'Current R phase' in meter_df.columns else 0.00
                cy = meter_df['Current Y phase'].iloc[0] if 'Current Y phase' in meter_df.columns else 0.00
                cb = meter_df['Current B phase'].iloc[0] if 'Current B phase' in meter_df.columns else 0.00
                ct = meter_df['Current Total'].iloc[0] if 'Current Total' in meter_df.columns else 0.00
                wr = meter_df['Watts R phase'].iloc[0] if 'Watts R phase' in meter_df.columns else 0.00
                wy = meter_df['Watts Y phase'].iloc[0] if 'Watts Y phase' in meter_df.columns else 0.00
                wb = meter_df['Watts B phase'].iloc[0] if 'Watts B phase' in meter_df.columns else 0.00
                wt = meter_df['Watts Total'].iloc[0] if 'Watts Total' in meter_df.columns else 0.00
                pfr = meter_df['PF R phase'].iloc[0] if 'PF R phase' in meter_df.columns else 0.00
                pfy = meter_df['PF Y phase'].iloc[0] if 'PF Y phase' in meter_df.columns else 0.00
                pfb = meter_df['PF B phase'].iloc[0] if 'PF B phase' in meter_df.columns else 0.00
                pfa = meter_df['PF Average Received'].iloc[0] if 'PF Average Received' in meter_df.columns else 0.00
                wh = meter_df['Wh Received'].iloc[0] if 'Wh Received' in meter_df.columns else (meter_df['Wh Received (Import)'].iloc[0] if 'Wh Received (Import)' in meter_df.columns else 0.00)
                vah = meter_df['VAh Received'].iloc[0] if 'VAh Received' in meter_df.columns else (meter_df['VAh Received (Import)'].iloc[0] if 'VAh Received (Import)' in meter_df.columns else 0.00)
                varhi = meter_df['VARh Ind Received'].iloc[0] if 'VARh Ind Received' in meter_df.columns else (meter_df['VARh Ind Received (Import)'].iloc[0] if 'VARh Ind Received (Import)' in meter_df.columns else 0.00)
                varhc = meter_df['VARh Cap Received'].iloc[0] if 'VARh Cap Received' in meter_df.columns else (meter_df['VARh Cap Received (Import)'].iloc[0] if 'VARh Cap Received (Import)' in meter_df.columns else 0.00)

                return (status_alert,
                        f"{vry:.2f}", f"{vyb:.2f}", f"{vbr:.2f}", f"{vll:.2f}",
                        f"{vr:.2f}", f"{vy:.2f}", f"{vb:.2f}", f"{vln:.2f}",
                        f"{cr:.2f}", f"{cy:.2f}", f"{cb:.2f}", f"{ct:.2f}",
                        f"{wr:.2f}", f"{wy:.2f}", f"{wb:.2f}", f"{wt:.2f}",
                        f"{pfr:.2f}", f"{pfy:.2f}", f"{pfb:.2f}", f"{pfa:.2f}",
                        f"{wh:.2f}", f"{vah:.2f}", f"{varhi:.2f}", f"{varhc:.2f}")
            except Exception as e:
                audit_logger.error(f"Error in update_meter_data for meter {current_meter_id}: {e}")
                return (html.Div(f"Error loading data for meter {current_meter_id}: {e}"),) + ("0.00",) * 24