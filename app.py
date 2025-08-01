import dash
from dash import dcc, html, Dash
from dash.dependencies import Input, Output, State
import pandas as pd
import plotly.express as px
import dash_bootstrap_components as dbc
import dash_auth
import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import logging
import os
import numpy as np
import warnings
from datalogger import get_yesterday_data, get_today_data, export_to_csv

# Suppress FutureWarning from Plotly
warnings.filterwarnings("ignore", category=FutureWarning)

# Load encryption key from file
KEY_FILE = '/home/sseevri/SmartSubstationMonitoringSystem/config_key.key'
if not os.path.exists(KEY_FILE):
    raise FileNotFoundError(f"Encryption key file {KEY_FILE} not found. Run encrypt_config.py first.")
with open(KEY_FILE, 'rb') as f:
    key = f.read()

# Load and decrypt configuration
with open('/home/sseevri/SmartSubstationMonitoringSystem/config.json', 'r') as f:
    encrypted_config = json.load(f)
cipher = Fernet(key)
config = json.loads(cipher.decrypt(encrypted_config['encrypted_data'].encode()).decode())

# Configure audit logging
audit_logger = logging.getLogger('audit')
audit_logger.setLevel(logging.INFO)
audit_handler = logging.FileHandler(config['audit_log_file'])
audit_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
audit_logger.addHandler(audit_handler)

# Initialize the Dash app
app = Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Set Flask secret key for session management
app.server.config['SECRET_KEY'] = os.urandom(24).hex()

# Basic authentication
VALID_USERNAME_PASSWORD_PAIRS = config['dashboard_auth']
auth = dash_auth.BasicAuth(app, VALID_USERNAME_PASSWORD_PAIRS)

# Define meter names
meter_names = {
    1: "Transformer",
    2: "EssentialLoad",
    3: "NonEssentialLoad",
    4: "ColonyLoad",
    5: "DGSetLoad"
}

# Define RYB-inspired color palette
RYB_COLORS = {
    "red": "#E34234",
    "yellow": "#FFD700",
    "blue": "#007FFF",
    "green": "#32CD32",
    "purple": "#8A2BE2",
    "dark_text": "#343a40",
    "light_bg": "#f8f9fa",
    "card_bg": "#ffffff",
    "dark_bg": "#343a40"
}

# Map parameters to phase colors
PHASE_COLORS = {
    "Watts R phase": "red",
    "Watts Y phase": "yellow",
    "Watts B phase": "blue",
    "VAR R phase": "red",
    "VAR Y phase": "yellow",
    "VAR B phase": "blue",
    "PF R phase": "red",
    "PF Y phase": "yellow",
    "PF B phase": "blue",
    "VA R phase": "red",
    "VA Y phase": "yellow",
    "VA B phase": "blue",
    "Vry Phase": "red",
    "Vyb Phase": "yellow",
    "Vbr Phase": "blue",
    "V R phase": "red",
    "V Y phase": "yellow",
    "V B phase": "blue",
    "Current R phase": "red",
    "Current Y phase": "yellow",
    "Current B phase": "blue"
}

# --- Data Loading Functions ---
def load_latest_csv_data():
    """Loads the latest data from CSV with 1-hour retention."""
    csv_file = config['csv_file']
    try:
        if not os.path.exists(csv_file):
            audit_logger.error(f"CSV file {csv_file} does not exist")
            return pd.DataFrame()
        if os.path.getsize(csv_file) == 0:
            audit_logger.error(f"CSV file {csv_file} is empty")
            return pd.DataFrame()
        df = pd.read_csv(csv_file)
        if df.empty:
            audit_logger.error(f"CSV file {csv_file} contains no data")
            return pd.DataFrame()
        df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
        cutoff_time = datetime.now() - timedelta(hours=1)
        df = df[df['DateTime'] >= cutoff_time]
        # Ensure non-negative values
        for col in df.columns:
            if col not in ['Date', 'Time', 'DateTime', 'Meter_ID', 'comm_status', 'status']:
                df[col] = df[col].astype(float).clip(lower=0)
        audit_logger.info(f"Successfully loaded CSV data from {csv_file}")
        return df
    except pd.errors.EmptyDataError:
        audit_logger.error(f"CSV load error: No columns to parse from file {csv_file}")
        return pd.DataFrame()
    except Exception as e:
        audit_logger.error(f"CSV load error: {e}")
        return pd.DataFrame()

# --- Layouts ---
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Home", href="/")),
        dbc.DropdownMenu(
            children=[
                dbc.DropdownMenuItem(f"{meter_names[mid]} (ID: {mid})", href=f"/meter/{mid}")
                for mid in [1, 2, 3, 4, 5]
            ],
            nav=True,
            in_navbar=True,
            label="Meter Pages",
        ),
        dbc.NavItem(dbc.Switch(id="theme-toggle", label="Dark Theme", value=False)),
    ],
    brand="Smart Substation Monitoring",
    brand_href="/",
    color="primary",
    dark=True,
    className="mb-4"
)

main_layout = dbc.Container([
    navbar,
    html.H1("Dashboard Overview", className="text-center my-4", style={'color': RYB_COLORS['dark_text']}),
    dcc.Store(id='theme-store', storage_type='local'),
    dcc.Store(id='selected-meters', data=[1, 2, 3, 4, 5]),
    # Temporarily disable session timeout
    # dcc.Store(id='session-timestamp', storage_type='session'),
    # html.Div(id='session-timeout-message', style={'display': 'none'}),
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader(html.H2("Status Summary", className="card-title")),
                dbc.CardBody(html.Div(id='status-summary'))
            ], className="shadow-sm"),
            md=12, className="mb-4"
        )
    ]),
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader(html.H2("Download SQLite Data", className="card-title")),
                dbc.CardBody([
                    dbc.Input(id="download-password", type="password", placeholder="Enter download password", className="mb-2"),
                    dbc.Button("Download as CSV", id="download-button", color="primary", className="me-2"),
                    html.Div(id="download-status"),
                    dcc.Download(id="download-csv")
                ])
            ], className="shadow-sm"),
            md=12, className="mb-4"
        )
    ]),
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader(html.H2("Current Readings (from CSV)", className="card-title")),
                dbc.CardBody(html.Div(id='live-update-csv-data'))
            ], className="shadow-sm"),
            md=12, className="mb-4"
        )
    ]),
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader([
                    html.H2("Chart Filters", className="card-title"),
                    dcc.Dropdown(
                        id='meter-filter',
                        options=[{'label': meter_names[mid], 'value': mid} for mid in [1, 2, 3, 4, 5]],
                        value=[1, 2, 3, 4, 5],
                        multi=True,
                        className="mt-2"
                    )
                ]),
                dbc.CardBody([
                    html.Div([
                        dbc.Button("Show/Hide Yesterday's Charts", id="collapse-yesterday-button", className="mb-2"),
                        dbc.Collapse([
                            dcc.Graph(id='yesterday-chart-vll'),
                            dcc.Graph(id='yesterday-chart-current'),
                            dcc.Graph(id='yesterday-chart-watts'),
                            dcc.Graph(id='yesterday-chart-pf'),
                        ], id="collapse-yesterday", is_open=True)
                    ]),
                    html.Div([
                        dbc.Button("Show/Hide Today's Charts", id="collapse-today-button", className="mb-2"),
                        dbc.Collapse([
                            dcc.Graph(id='today-chart-vll'),
                            dcc.Graph(id='today-chart-current'),
                            dcc.Graph(id='today-chart-watts'),
                            dcc.Graph(id='today-chart-pf'),
                        ], id="collapse-today", is_open=True)
                    ])
                ])
            ], className="shadow-sm"),
            md=12, className="mb-4"
        )
    ]),
    dcc.Interval(
        id='interval-component-csv',
        interval=10*1000,  # Increased to 10s to reduce load
        n_intervals=0
    ),
    dcc.Interval(
        id='interval-component-db',
        interval=120*1000,  # Increased to 2min to reduce load
        n_intervals=0
    ),
    # Temporarily disable session timeout
    # dcc.Interval(
    #     id='session-timeout-interval',
    #     interval=1000*60,  # Check every minute
    #     n_intervals=0
    # )
], fluid=True, id='main-container', style={'backgroundColor': RYB_COLORS['light_bg'], 'minHeight': '100vh'})

def create_meter_layout(meter_id):
    return dbc.Container([
        navbar,
        html.H1(f"{meter_names[meter_id]} - Meter ID: {meter_id}", className="text-center my-4", style={'color': RYB_COLORS['dark_text']}),
        dcc.Store(id='theme-store', storage_type='local'),
        # dcc.Store(id='session-timestamp', storage_type='session'),
        html.Div(id=f'meter-{meter_id}-status', className="text-center mb-3"),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(html.H2("All Parameters (from CSV)", className="card-title")),
                    dbc.CardBody(html.Div(id=f'meter-{meter_id}-data'))
                ], className="shadow-sm"),
                md=12, className="mb-4"
            )
        ]),
        dcc.Interval(
            id=f'interval-meter-{meter_id}',
            interval=10*1000,  # Increased to 10s to reduce load
            n_intervals=0
        )
    ], fluid=True, id='main-container', style={'backgroundColor': RYB_COLORS['light_bg'], 'minHeight': '100vh'})

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

# Temporarily disable session timeout callback
# app.clientside_callback(
#     """
#     function(n_intervals, session_timestamp) {
#         if (!session_timestamp) {
#             session_timestamp = new Date().getTime();
#             return [session_timestamp, ''];
#         }
#         const current_time = new Date().getTime();
#         const session_duration = (current_time - session_timestamp) / 1000; // in seconds
#         const timeout_duration = 1800; // 30 minutes
#         if (session_duration > timeout_duration) {
#             window.location.href = '/';
#             return [session_timestamp, 'Session expired. Please log in again.'];
#         }
#         return [session_timestamp, ''];
#     }
#     """,
#     [Output('session-timestamp', 'data'),
#      Output('session-timeout-message', 'children')],
#     Input('session-timeout-interval', 'n_intervals'),
#     State('session-timestamp', 'data')
# )

# --- Callbacks ---
@app.callback(Output('page-content', 'children'),
              Input('url', 'pathname'))
def display_page(pathname):
    try:
        audit_logger.info(f"Page access: {pathname}")
        if pathname == '/':
            return main_layout
        elif pathname.startswith('/meter/'):
            meter_id = int(pathname.split('/')[-1])
            return create_meter_layout(meter_id)
        else:
            return html.H1("404 - Page Not Found")
    except Exception as e:
        audit_logger.error(f"Error in page access: {e}")
        return html.H1("Error loading page")

@app.callback(
    [Output('download-csv', 'data'),
     Output('download-status', 'children')],
    [Input('download-button', 'n_clicks')],
    [State('download-password', 'value')]
)
def download_csv(n_clicks, password):
    try:
        if n_clicks is None:
            return None, ""
        audit_logger.info(f"CSV download attempt")
        if password != config['download_password']:
            audit_logger.warning(f"Failed CSV download attempt")
            return None, dbc.Alert("Incorrect password", color="danger")
        csv_data = export_to_csv(config['db_path'])
        if csv_data is None:
            audit_logger.error(f"Failed CSV export")
            return None, dbc.Alert("Error exporting data", color="danger")
        audit_logger.info(f"Successful CSV download")
        return dcc.send_string(csv_data, "meter_data_1year.csv"), dbc.Alert("Download started", color="success")
    except Exception as e:
        audit_logger.error(f"Error in download_csv callback: {e}")
        return None, dbc.Alert(f"Error in download: {e}", color="danger")

@app.callback(
    Output('status-summary', 'children'),
    Input('interval-component-csv', 'n_intervals')
)
def update_status_summary(n):
    try:
        df = load_latest_csv_data()
        if df.empty:
            audit_logger.warning("No status data available in update_status_summary")
            return html.Div("No status data available.")
        status_counts = df.groupby('Meter_ID').last()['status'].value_counts()
        comm_failed = df.groupby('Meter_ID').last()['comm_status'].eq('FAILED').sum()
        badges = [
            dbc.Badge(f"OK: {status_counts.get('OK', 0)}", color=RYB_COLORS['green'], className="me-1"),
            dbc.Badge(f"Power Failure: {status_counts.get('POWER_FAIL', 0)}", color=RYB_COLORS['yellow'], className="me-1"),
            dbc.Badge(f"Communication Failed: {comm_failed}", color=RYB_COLORS['red'], className="me-1")
        ]
        return html.Div(badges)
    except Exception as e:
        audit_logger.error(f"Error in update_status_summary: {e}")
        return html.Div(f"Error loading status summary: {e}")

@app.callback(
    Output('live-update-csv-data', 'children'),
    Input('interval-component-csv', 'n_intervals')
)
def update_main_csv_data(n):
    try:
        df = load_latest_csv_data()
        if df.empty:
            audit_logger.warning("No CSV data available for main page update")
            return html.Div("No CSV data available.")

        main_params = ["VLL Average", "Current Total", "Watts Total", "PF Average Received"]
        latest_readings = df.groupby('Meter_ID').last().reset_index()
        all_meter_ids = [1, 2, 3, 4, 5]
        display_data = []

        for mid in all_meter_ids:
            meter_row = latest_readings[latest_readings['Meter_ID'] == mid]
            if not meter_row.empty:
                display_data.append(meter_row.iloc[0])
            else:
                dummy_row = {'Meter_ID': mid, 'comm_status': 'FAILED', 'status': 'FAILED'}
                for param in main_params:
                    dummy_row[param] = "No data available"
                display_data.append(dummy_row)

        connected_meters_df = pd.DataFrame(display_data)
        connected_meters_df = connected_meters_df.sort_values(by='Meter_ID').reset_index(drop=True)

        table_header = [html.Thead(html.Tr([html.Th("Meter Name"), html.Th("Meter ID"), html.Th("Status")] + [html.Th(param) for param in main_params]))]
        table_rows = []

        for index, row in connected_meters_df.iterrows():
            meter_id = row['Meter_ID']
            status = "Communication Failed" if row['comm_status'] == "FAILED" else row['status']
            status_color = "red" if status == "Communication Failed" else "yellow" if status == "POWER_FAIL" else "green"
            status_badge = dbc.Badge(status, color=RYB_COLORS[status_color], className="me-1", title=status)
            row_data = [html.Td(meter_names.get(meter_id, f"Unknown ({meter_id})")), html.Td(meter_id), html.Td(status_badge)]
            for param in main_params:
                value = row[param]
                row_data.append(html.Td(dbc.Badge(f"{value:.2f}" if isinstance(value, (int, float)) else str(value), color=RYB_COLORS['green'], className="me-1")))
            table_rows.append(html.Tr(row_data))

        table_body = [html.Tbody(table_rows)]
        return dbc.Table(table_header + table_body, bordered=True, hover=True, responsive=True, striped=True, className="table-sm")
    except Exception as e:
        audit_logger.error(f"Error in update_main_csv_data: {e}")
        return html.Div(f"Error loading main dashboard data: {e}")

@app.callback(
    [Output('yesterday-chart-vll', 'figure'),
     Output('yesterday-chart-current', 'figure'),
     Output('yesterday-chart-watts', 'figure'),
     Output('yesterday-chart-pf', 'figure'),
     Output('today-chart-vll', 'figure'),
     Output('today-chart-current', 'figure'),
     Output('today-chart-watts', 'figure'),
     Output('today-chart-pf', 'figure'),
     Output('selected-meters', 'data')],
    [Input('interval-component-db', 'n_intervals'),
     Input('meter-filter', 'value')]
)
def update_db_charts(n, selected_meters):
    try:
        df_yesterday = get_yesterday_data(config['db_path'])
        df_today = get_today_data(config['db_daily_path'])
        if df_yesterday.empty and df_today.empty:
            audit_logger.warning("No DB data available for charts")
            return [{}]*8 + [selected_meters]

        df_yesterday['DateTime'] = np.array(pd.to_datetime(df_yesterday['DateTime']))
        df_today['DateTime'] = np.array(pd.to_datetime(df_today['DateTime']))
        df_yesterday = df_yesterday[df_yesterday['Meter_ID'].isin(selected_meters)]
        df_today = df_today[df_today['Meter_ID'].isin(selected_meters)]

        color_sequence = [RYB_COLORS["red"], RYB_COLORS["yellow"], RYB_COLORS["blue"], RYB_COLORS["green"], RYB_COLORS["purple"]]
        chart_params = [
            ('VLL Average', 'VLL Average (Volts)', (0, 500)),
            ('Current Total', 'Current Total (Amps)', (0, 1000)),
            ('Watts Total', 'Watts Total (Watts)', (0, 1000000)),
            ('PF Average Received', 'PF Average Received', (0, 1))
        ]

        figures = []
        for param, ylabel, yrange in chart_params:
            fig_yesterday = px.line(
                df_yesterday, x='DateTime', y=param, color='Meter_ID',
                title=f'Yesterday: {param}',
                labels={'DateTime': 'Time', param: ylabel, 'Meter_ID': 'Meter'},
                color_discrete_sequence=color_sequence,
                hover_data={'Meter_ID': False, param: ':.2f', 'DateTime': '|%Y-%m-%d %H:%M:%S', 'Meter_Name': df_yesterday['Meter_ID'].map(meter_names)}
            )
            fig_yesterday.update_yaxes(range=yrange, gridcolor='lightgray')
            fig_yesterday.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig_yesterday.update_layout(hovermode='x unified')
            figures.append(fig_yesterday)

            fig_today = px.line(
                df_today, x='DateTime', y=param, color='Meter_ID',
                title=f'Today: {param}',
                labels={'DateTime': 'Time', param: ylabel, 'Meter_ID': 'Meter'},
                color_discrete_sequence=color_sequence,
                hover_data={'Meter_ID': False, param: ':.2f', 'DateTime': '|%Y-%m-%d %H:%M:%S', 'Meter_Name': df_today['Meter_ID'].map(meter_names)}
            )
            fig_today.update_yaxes(range=yrange, gridcolor='lightgray')
            fig_today.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig_today.update_layout(hovermode='x unified')
            figures.append(fig_today)

        return figures + [selected_meters]
    except Exception as e:
        audit_logger.error(f"Error in update_db_charts: {e}")
        return [{}]*8 + [selected_meters]

@app.callback(
    [Output('collapse-yesterday', 'is_open'),
     Output('collapse-yesterday-button', 'children')],
    [Input('collapse-yesterday-button', 'n_clicks')],
    [State('collapse-yesterday', 'is_open')]
)
def toggle_collapse_yesterday(n_clicks, is_open):
    try:
        if n_clicks:
            return not is_open, "Show Yesterday's Charts" if is_open else "Hide Yesterday's Charts"
        return is_open, "Hide Yesterday's Charts" if is_open else "Show Yesterday's Charts"
    except Exception as e:
        audit_logger.error(f"Error in toggle_collapse_yesterday: {e}")
        return is_open, "Hide Yesterday's Charts" if is_open else "Show Yesterday's Charts"

@app.callback(
    [Output('collapse-today', 'is_open'),
     Output('collapse-today-button', 'children')],
    [Input('collapse-today-button', 'n_clicks')],
    [State('collapse-today', 'is_open')]
)
def toggle_collapse_today(n_clicks, is_open):
    try:
        if n_clicks:
            return not is_open, "Show Today's Charts" if is_open else "Hide Today's Charts"
        return is_open, "Hide Today's Charts" if is_open else "Show Today's Charts"
    except Exception as e:
        audit_logger.error(f"Error in toggle_collapse_today: {e}")
        return is_open, "Hide Today's Charts" if is_open else "Show Today's Charts"

@app.callback(
    [Output('main-container', 'style'),
     Output('theme-store', 'data')],
    [Input('theme-toggle', 'value')],
    [State('theme-store', 'data')]
)
def toggle_theme(dark_theme, stored_theme):
    try:
        if dark_theme:
            return {'backgroundColor': RYB_COLORS['dark_bg'], 'color': RYB_COLORS['light_bg'], 'minHeight': '100vh'}, {'theme': 'dark'}
        return {'backgroundColor': RYB_COLORS['light_bg'], 'color': RYB_COLORS['dark_text'], 'minHeight': '100vh'}, {'theme': 'light'}
    except Exception as e:
        audit_logger.error(f"Error in toggle_theme: {e}")
        return {'backgroundColor': RYB_COLORS['light_bg'], 'color': RYB_COLORS['dark_text'], 'minHeight': '100vh'}, {'theme': 'light'}

for meter_id in [1, 2, 3, 4, 5]:
    @app.callback(
        [Output(f'meter-{meter_id}-data', 'children'),
         Output(f'meter-{meter_id}-status', 'children')],
        Input(f'interval-meter-{meter_id}', 'n_intervals')
    )
    def update_meter_data(n, current_meter_id=meter_id):
        try:
            df = load_latest_csv_data()
            if df.empty:
                audit_logger.warning(f"No CSV data available for meter {current_meter_id} page update")
                return html.Div("No CSV data available."), html.Div()

            meter_df = df[df['Meter_ID'] == current_meter_id].tail(1).reset_index()
            if meter_df.empty:
                audit_logger.warning(f"No data available for Meter ID {current_meter_id} after filtering")
                return html.Div(f"No data available for Meter ID {current_meter_id}."), html.Div()

            status = "Communication Failed" if meter_df.iloc[0]['comm_status'] == "FAILED" else meter_df.iloc[0]['status']
            status_color = "red" if status == "Communication Failed" else "yellow" if status == "POWER_FAIL" else "green"
            status_alert = html.Div(
                dbc.Alert(status, color=RYB_COLORS[status_color], className="fade show"),
                className="text-center"
            ) if status != "OK" else html.Div()

            table_header = [html.Thead(html.Tr([html.Th("Parameter"), html.Th("Value")]))]
            table_rows = []
            exclude_cols = ['index', 'Date', 'Time', 'DateTime', 'Meter_ID', 'comm_status', 'status']
            for col in meter_df.columns:
                if col not in exclude_cols:
                    value = meter_df.iloc[0][col]
                    color = PHASE_COLORS.get(col, "green")
                    table_rows.append(html.Tr([
                        html.Td(col),
                        html.Td(dbc.Badge(f"{value:.2f}" if isinstance(value, (int, float)) else str(value), color=RYB_COLORS[color], className="me-1 p-2", title=col))
                    ]))

            table_body = [html.Tbody(table_rows)]
            return dbc.Table(table_header + table_body, bordered=True, hover=True, responsive=True, striped=True, className="table-sm"), status_alert
        except Exception as e:
            audit_logger.error(f"Error in update_meter_data for meter {current_meter_id}: {e}")
            return html.Div(f"Error loading data for meter {current_meter_id}: {e}"), html.Div()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050, dev_tools_prune_errors=True)
