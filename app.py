import dash
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import dcc, html, Dash
from dash.dependencies import Input, Output, State
import pandas as pd
import plotly.express as px
import dash_bootstrap_components as dbc
import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import logging
import os
import numpy as np
import warnings
from werkzeug.security import check_password_hash
import sqlite3
from datalogger import get_yesterday_data, get_today_data, export_to_csv

# Suppress Plotly FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning)

# Load encryption key
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

# Initialize Dash app
app = Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP, '/assets/voltmeter.css', 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css'])
app.server.config['SECRET_KEY'] = os.urandom(24).hex()

# Basic authentication credentials
VALID_USERNAME_PASSWORD_PAIRS = config['dashboard_auth']

# Meter names
meter_names = {
    1: "Transformer",
    2: "EssentialLoad",
    3: "NonEssentialLoad",
    4: "ColonyLoad",
    5: "DGSetLoad"
}

# Color palette
RYB_COLORS = {
    "red": "#E34234",
    "yellow": "#FFD700",
    "blue": "#007FFF",
    "green": "#32CD32",
    "purple": "#8A2BE2",
    "dark_text": "#343a40",
    "light_bg": "#f8f9fa",
    "card_bg": "#ffffff",
    "dark_bg": "#343a40",
    "danger": "#E34234",
    "success": "#32CD32",
    "secondary": "#6c757d"
}

# Phase colors
PHASE_COLORS = {
    "Watts R phase": "red", "Watts Y phase": "yellow", "Watts B phase": "blue",
    "VAR R phase": "red", "VAR Y phase": "yellow", "VAR B phase": "blue",
    "PF R phase": "red", "PF Y phase": "yellow", "PF B phase": "blue",
    "VA R phase": "red", "VA Y phase": "yellow", "VA B phase": "blue",
    "Vry Phase": "blue", "Vyb Phase": "yellow", "Vbr Phase": "red",
    "V R phase": "red", "V Y phase": "yellow", "V B phase": "blue",
    "Current R phase": "red", "Current Y phase": "yellow", "Current B phase": "blue"
}

# Load CSV data
def load_latest_csv_data():
    csv_file = config['csv_file']
    audit_logger.info(f"Attempting to load CSV from: {csv_file}")
    try:
        if not os.path.exists(csv_file):
            audit_logger.error(f"CSV file {csv_file} does not exist")
            return pd.DataFrame()
        if os.path.getsize(csv_file) == 0:
            audit_logger.error(f"CSV file {csv_file} is empty")
            return pd.DataFrame()
        df = pd.read_csv(csv_file)
        audit_logger.info(f"Type of df after pd.read_csv: {type(df)}")
        if not isinstance(df, pd.DataFrame):
            audit_logger.error(f"pd.read_csv did not return a DataFrame for {csv_file}. Type: {type(df)}")
            return pd.DataFrame()
        if df.empty:
            audit_logger.error(f"CSV file {csv_file} contains no data")
            return pd.DataFrame()
        audit_logger.info(f"Type of df before empty check in load_latest_csv_data: {type(df)}")
        df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
        cutoff_time = datetime.now() - timedelta(hours=1)
        df = df[df['DateTime'] >= cutoff_time]
        for col in df.columns:
            if col not in ['Date', 'Time', 'DateTime', 'Meter_ID', 'comm_status', 'status']:
                audit_logger.info(f"Type of df[{col}]: {type(df[col])}")
                if df[col].dtype == 'object':
                    try:
                        df[col] = pd.to_datetime(df[col])
                    except ValueError:
                        pass
        audit_logger.info(f"Successfully loaded CSV data from {csv_file}")
        audit_logger.info(f"Returning df from load_latest_csv_data: {df.head()}")
        return df
    except pd.errors.EmptyDataError:
        audit_logger.error(f"CSV load error: No columns to parse from file {csv_file}")
        return pd.DataFrame()
    except Exception as e:
        audit_logger.error(f"CSV load error: {e}")
        return pd.DataFrame()

# Add this new function to app.py after the load_latest_csv_data function
def get_energy_consumption(db_path, date_str):
    '''Calculate energy consumption for a specific date for all meters.'''
    try:
        with sqlite3.connect(db_path) as conn:
            query = '''
            SELECT Meter_ID, MIN("Wh Received") as min_wh, MAX("Wh Received") as max_wh
            FROM meter_readings
            WHERE DATE(DateTime) = ?
            GROUP BY Meter_ID
            '''
            df = pd.read_sql_query(query, conn, params=(date_str,))
        
        # Calculate consumption in kWh
        consumption = {}
        for _, row in df.iterrows():
            meter_id = row['Meter_ID']
            min_wh = row['min_wh'] if pd.notna(row['min_wh']) else 0
            max_wh = row['max_wh'] if pd.notna(row['max_wh']) else 0
            consumption[meter_id] = max((max_wh - min_wh) / 1000, 0)  # Convert to kWh, ensure non-negative
        
        return consumption
    except Exception as e:
        audit_logger.error(f"Error calculating energy consumption for {date_str}: {e}")
        return {}

# Add this new function to create the energy consumption table
def create_energy_consumption_table(consumption_data, title):
    '''Create a table showing energy consumption for all meters.'''
    table_header = [html.Thead(html.Tr([
        html.Th("Meter Name", className="large-font"),
        html.Th(title, className="large-font")
    ]))]
    
    table_rows = []
    for meter_id in [1, 2, 3, 4, 5]:
        meter_name = meter_names.get(meter_id, f"Unknown ({meter_id})")
        consumption = consumption_data.get(meter_id, 0.0)
        table_rows.append(html.Tr([
            html.Td(meter_name, className="large-font"),
            html.Td(f"{consumption:.2f} kWh", className="large-font")
        ]))
    
    table_body = [html.Tbody(table_rows)]
    return dbc.Table(table_header + table_body, bordered=True, hover=True, responsive=True, striped=True, className="table-sm")

def create_energy_card(meter_id, meter_name, yesterday_energy, today_energy):
    """Create a beautiful card for energy consumption with progress bar and comparison."""
    # Calculate percentage change
    if yesterday_energy > 0:
        change_percent = ((today_energy - yesterday_energy) / yesterday_energy) * 100
    else:
        change_percent = 0 if today_energy == 0 else 100  # If yesterday was 0 and today has value
    
    # Determine change direction and color
    if change_percent > 0:
        change_direction = "up"
        change_color = "danger"
        change_icon = "arrow-up"
    elif change_percent < 0:
        change_direction = "down"
        change_color = "success"
        change_icon = "arrow-down"
    else:
        change_direction = "equal"
        change_color = "secondary"
        change_icon = "arrow-right"
    
    # Determine progress bar color based on consumption level
    if today_energy < 100:
        progress_color = "success"
    elif today_energy < 300:
        progress_color = "warning"
    else:
        progress_color = "danger"
    
    # Create a progress bar (assuming max consumption of 500 kWh for visualization)
    progress_value = min(today_energy / 500 * 100, 100)
    
    # Create the card
    card = dbc.Card([
        dbc.CardBody([
            html.Div([
                # Meter name and icon
                html.Div([
                    html.I(className="fas fa-bolt me-2", style={"color": RYB_COLORS['blue']}),
                    html.H5(meter_name, className="mb-0")
                ], className="d-flex align-items-center"),
                
                # Energy values
                html.Div([
                    html.Div([
                        html.Span("Yesterday:", className="text-muted small"),
                        html.H4(f"{yesterday_energy:.2f} kWh", className="mb-0")
                    ], className="text-center"),
                    html.Div([
                        html.Span("Today:", className="text-muted small"),
                        html.H4(f"{today_energy:.2f} kWh", className="mb-0")
                    ], className="text-center")
                ], className="d-flex justify-content-between mt-2"),
                
                # Change indicator
                html.Div([
                    html.I(className=f"fas fa-{change_icon} me-1", style={"color": RYB_COLORS[change_color]}),
                    html.Span(f"{abs(change_percent):.1f}%", style={"color": RYB_COLORS[change_color]})
                ], className="text-center mt-2"),
                
                # Progress bar
                dbc.Progress(
                    value=progress_value,
                    color=progress_color,
                    className="mt-2",
                    style={"height": "10px"}
                )
            ])
        ])
    ], className="h-100 shadow-sm")
    
    return card

# Update the energy consumption section in the main layout
def create_energy_consumption_layout(yesterday_consumption, today_consumption):
    """Create the energy consumption layout with beautiful cards."""
    # Create cards for each meter
    cards = []
    for meter_id in [1, 2, 3, 4, 5]:
        meter_name = meter_names.get(meter_id, f"Unknown ({meter_id})")
        yesterday_energy = yesterday_consumption.get(meter_id, 0.0)
        today_energy = today_consumption.get(meter_id, 0.0)
        
        card = create_energy_card(meter_id, meter_name, yesterday_energy, today_energy)
        cards.append(dbc.Col(card, className="mb-4", width=12, md=6, lg=4, xl=2))
    
    # Create a summary row with total consumption
    total_yesterday = sum(yesterday_consumption.values())
    total_today = sum(today_consumption.values())
    
    # Calculate total change
    if total_yesterday > 0:
        total_change_percent = ((total_today - total_yesterday) / total_yesterday) * 100
    else:
        total_change_percent = 0 if total_today == 0 else 100
    
    # Determine total change direction and color
    if total_change_percent > 0:
        total_change_direction = "up"
        total_change_color = "danger"
        total_change_icon = "arrow-up"
    elif total_change_percent < 0:
        total_change_direction = "down"
        total_change_color = "success"
        total_change_icon = "arrow-down"
    else:
        total_change_direction = "equal"
        total_change_color = "secondary"
        total_change_icon = "arrow-right"
    
    # Create a summary card
    summary_card = dbc.Card([
        dbc.CardBody([
            html.H4("Total Energy Consumption", className="text-center mb-3"),
            html.Div([
                html.Div([
                    html.Span("Yesterday:", className="text-muted small"),
                    html.H3(f"{total_yesterday:.2f} kWh", className="mb-0 text-center")
                ], className="mb-2"),
                html.Div([
                    html.Span("Today:", className="text-muted small"),
                    html.H3(f"{total_today:.2f} kWh", className="mb-0 text-center")
                ], className="mb-2"),
                html.Div([
                    html.I(className=f"fas fa-{total_change_icon} me-1", style={"color": RYB_COLORS[total_change_color]}),
                    html.Span(f"{abs(total_change_percent):.1f}%", style={"color": RYB_COLORS[total_change_color]})
                ], className="text-center")
            ])
        ])
    ], className="shadow-sm")
    
    # Create a pie chart for energy distribution
    pie_data = []
    for meter_id in [1, 2, 3, 4, 5]:
        meter_name = meter_names.get(meter_id, f"Unknown ({meter_id})")
        energy = today_consumption.get(meter_id, 0.0)
        if energy > 0:
            pie_data.append({"Meter": meter_name, "Energy": energy})
    
    if pie_data:
        pie_df = pd.DataFrame(pie_data)
        pie_fig = px.pie(
            pie_df, 
            values="Energy", 
            names="Meter", 
            title="Today's Energy Distribution",
            color_discrete_sequence=[RYB_COLORS["red"], RYB_COLORS["yellow"], RYB_COLORS["blue"], RYB_COLORS["green"], RYB_COLORS["purple"]]
        )
        pie_fig.update_traces(textposition='inside', textinfo='percent+label')
        pie_fig.update_layout(
            margin=dict(l=0, r=0, t=40, b=0),
            height=250
        )
        pie_chart = dcc.Graph(figure=pie_fig, style={"height": "250px"})
    else:
        pie_chart = html.Div("No data available", className="text-center p-4")
    
    # Return the complete layout
    return html.Div([
        dbc.Row([
            dbc.Col(summary_card, className="mb-4", width=12, lg=4),
            dbc.Col(pie_chart, className="mb-4", width=12, lg=8)
        ]),
        dbc.Row(cards)
    ])


# Layouts
login_layout = html.Div([
    html.Div([
        html.Img(src='/assets/Vridhachalam.png', style={'position': 'fixed', 'top': 0, 'left': 0, 'width': '100%', 'height': '100%', 'z-index': -1, 'opacity': 0.4}),
        html.Div([
            html.H2("SSE/E/VRI Smart Substation Monitoring", className="text-center text-white"),
            dbc.Card([
                dbc.CardBody([
                    dbc.Input(id="login-username", placeholder="Username", type="text", className="mb-3"),
                    dbc.Input(id="login-password", placeholder="Password", type="password", className="mb-3"),
                    dbc.Button("Login", id="login-button", color="primary", className="w-100"),
                    html.Div(id="login-output", className="text-danger mt-2 text-center")
                ])
            ], className="shadow-lg p-4 bg-dark bg-opacity-75", style={'max-width': '400px', 'margin': 'auto', 'border-radius': '10px'})
        ], className="d-flex justify-content-center align-items-center min-vh-100")
    ], className="login-page")
], style={'background-color': '#000', 'position': 'relative'})

navbar = dbc.NavbarSimple(
    id='main-navbar',
    children=[
        dbc.NavItem(dbc.NavLink("Home", href="/", style={'color': 'white', 'fontWeight': 'bold'})),
        dbc.DropdownMenu(
            children=[
                dbc.DropdownMenuItem(f"{meter_names[mid]} (ID: {mid})", href=f"/meter/{mid}")
                for mid in [1, 2, 3, 4, 5]
            ],
            nav=True,
            in_navbar=True,
            label=html.Span("Meter Pages", style={'color': 'white', 'fontWeight': 'bold'}),
        ),
        dbc.NavItem(dbc.Switch(id="theme-toggle", label="Dark Theme", value=False)),
    ],
    brand=html.Span("SSE/E/VRI Smart Substation Monitoring", style={'color': 'white', 'fontWeight': 'bold'}),
    brand_href="/",
    color="primary",
    dark=True,
    className="mb-4"
)

main_layout = dbc.Container([
    navbar,
    dbc.Row([
        dbc.Col(html.Img(src='/assets/southern_railway.png', height='100px'), width=2, className="text-start"),
        dbc.Col(html.H1("Dashboard Overview", className="text-center my-4"), width=8),
        dbc.Col(html.Img(src='/assets/Indian Railway Logo.jpg', height='100px'), width=2, className="text-end")
    ], align="center"),
    dcc.Store(id='theme-store', storage_type='local'),
    dcc.Store(id='selected-meters', data=[1, 2, 3, 4, 5]),
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
                dbc.CardHeader(html.H2("Substation Meter Readings", className="card-title")),
                dbc.CardBody(html.Div(id='live-update-csv-data'))
            ], className="shadow-sm"),
            md=12, className="mb-4"
        )
    ]),
    # NEW SECTION: Energy Consumption with beautiful layout
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader(html.H2("Energy Consumption", className="card-title")),
                dbc.CardBody(html.Div(id='energy-consumption-layout'))
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
                    dbc.Row([
                        dbc.Col(dbc.Button("Show/Hide Yesterday's Charts", id="collapse-yesterday-button", className="mb-2"), width=6),
                        dbc.Col(dbc.Button("Show/Hide Today's Charts", id="collapse-today-button", className="mb-2"), width=6)
                    ]),
                    dbc.Collapse(dcc.Graph(id='yesterday-chart-vll'), id="collapse-yesterday-vll", is_open=True),
                    dbc.Collapse(dcc.Graph(id='today-chart-vll'), id="collapse-today-vll", is_open=True),
                    dbc.Collapse(dcc.Graph(id='yesterday-chart-current'), id="collapse-yesterday-current", is_open=True),
                    dbc.Collapse(dcc.Graph(id='today-chart-current'), id="collapse-today-current", is_open=True),
                    dbc.Collapse(dcc.Graph(id='yesterday-chart-watts'), id="collapse-yesterday-watts", is_open=True),
                    dbc.Collapse(dcc.Graph(id='today-chart-watts'), id="collapse-today-watts", is_open=True),
                    dbc.Collapse(dcc.Graph(id='yesterday-chart-pf'), id="collapse-yesterday-pf", is_open=True),
                    dbc.Collapse(dcc.Graph(id='today-chart-pf'), id="collapse-today-pf", is_open=True)
                ])
            ], className="shadow-sm"),
            md=12, className="mb-4"
        )
    ]),
    dcc.Interval(
        id='interval-component-csv',
        interval=10*1000,  # 10s for CSV updates
        n_intervals=0
    ),
    dcc.Interval(
        id='interval-component-db',
        interval=120*1000,  # 2min for DB updates
        n_intervals=0
    )
], fluid=True, id='main-container')

def create_meter_layout(meter_id):
    return dbc.Container([
        navbar,
        html.H1(f"{meter_names[meter_id]} - Meter ID: {meter_id}", className="text-center my-4"),
        dcc.Store(id='theme-store', storage_type='local'),
        html.Div(id=f'meter-{meter_id}-status', className="text-center mb-3"),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Line Voltage"),
                    dbc.CardBody([
                        html.Span("Vry Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vry', className='voltmeter-display'),
                        html.Span("Vyb Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vyb', className='voltmeter-display'),
                        html.Span("Vbr Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vbr', className='voltmeter-display'),
                        html.Span("VLL Average", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vll', className='voltmeter-display')
                    ])
                ], className="shadow-sm"),
                className="col-12 col-md-6 mb-4"
            ),
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Phase Voltage"),
                    dbc.CardBody([
                        html.Span("V R Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vr', className='voltmeter-display'),
                        html.Span("V Y Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vy', className='voltmeter-display'),
                        html.Span("V B Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vb', className='voltmeter-display'),
                        html.Span("VLN Average", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vln', className='voltmeter-display')
                    ])
                ], className="shadow-sm"),
                className="col-12 col-md-6 mb-4"
            )
        ]),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Current"),
                    dbc.CardBody([
                        html.Span("Current R Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-cr', className='voltmeter-display'),
                        html.Span("Current Y Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-cy', className='voltmeter-display'),
                        html.Span("Current B Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-cb', className='voltmeter-display'),
                        html.Span("Current Total", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-ct', className='voltmeter-display')
                    ])
                ], className="shadow-sm"),
                className="col-12 col-md-6 mb-4"
            ),
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Power"),
                    dbc.CardBody([
                        html.Span("KW R Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-wr', className='voltmeter-display'),
                        html.Span("KW Y Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-wy', className='voltmeter-display'),
                        html.Span("KW B Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-wb', className='voltmeter-display'),
                        html.Span("KW Total", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-wt', className='voltmeter-display')
                    ])
                ], className="shadow-sm"),
                className="col-12 col-md-6 mb-4"
            )
        ]),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Power Factor"),
                    dbc.CardBody([
                        html.Span("PF R Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-pfr', className='voltmeter-display'),
                        html.Span("PF Y Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-pfy', className='voltmeter-display'),
                        html.Span("PF B Phase", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-pfb', className='voltmeter-display'),
                        html.Span("PF Average", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-pfa', className='voltmeter-display')
                    ])
                ], className="shadow-sm"),
                className="col-12 col-md-6 mb-4"
            ),
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("Energy"),
                    dbc.CardBody([
                        html.Span("KWh Received", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-wh', className='voltmeter-display'),
                        html.Span("KVAh Received", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-vah', className='voltmeter-display'),
                        html.Span("KVARh Ind Received", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-varhi', className='voltmeter-display'),
                        html.Span("KVARh Cap Received", className='voltmeter-label'),
                        html.Div(id=f'meter-{meter_id}-varhc', className='voltmeter-display')
                    ])
                ], className="shadow-sm"),
                className="col-12 col-md-6 mb-4"
            )
        ]),
        dcc.Interval(
            id=f'interval-meter-{meter_id}',
            interval=10*1000,
            n_intervals=0
        )
    ], fluid=True, id='main-container', className="meter-container")

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='login-status', data=False, storage_type='session'),
    html.Div(id='page-content')
])

# Callbacks
@app.callback(
    Output('login-status', 'data'),
    Output('url', 'pathname'),
    Output('login-output', 'children'),
    Input('login-button', 'n_clicks'),
    State('login-username', 'value'),
    State('login-password', 'value'),
    prevent_initial_call=True
)
def login(n_clicks, username, password):
    if n_clicks and username and password:
        hashed_password = VALID_USERNAME_PASSWORD_PAIRS.get(username)
        audit_logger.info(f"Hashed password from config: {hashed_password}")
        audit_logger.info(f"Password from form: {password}")
        if hashed_password:
            try:
                # Use werkzeug's check_password_hash instead of scrypt.dehash
                if check_password_hash(hashed_password, password):
                    audit_logger.info(f"Successful login for user: {username}")
                    return True, '/', ''
            except Exception as e:
                audit_logger.error(f"Password verification error: {e}")
        audit_logger.warning(f"Failed login attempt for user: {username}")
        return False, '/login', 'Invalid username or password'
    return dash.no_update, dash.no_update, '' 

@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname'),
     Input('login-status', 'data')]
)
def display_page(pathname, login_status):
    if not login_status:
        return login_layout
    
    try:
        audit_logger.info(f"Page access: {pathname}")
        if pathname == '/' or pathname == '/login':
            return main_layout
        elif pathname.startswith('/meter/'):
            meter_id_str = pathname.split('/')[-1]
            if meter_id_str.isdigit():
                meter_id = int(meter_id_str)
                if meter_id in meter_names:
                    return create_meter_layout(meter_id)
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
        
        latest_readings = df.groupby('Meter_ID').last().reset_index()

        status_counts = latest_readings['status'].value_counts()
        comm_failed = latest_readings['comm_status'].eq('FAILED').sum()

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
        if not isinstance(df, pd.DataFrame):
            audit_logger.error(f"df in update_main_csv_data is not a DataFrame. Type: {type(df)}")
            return html.Div("Error: Data is not in expected format.")

        if df.empty:
            audit_logger.warning("No CSV data available for main page update")
            return html.Div("No CSV data available.")

        main_params = ["VLL Average", "Current Total", "Watts Total", "PF Average Received"]
        latest_readings = df.groupby('Meter_ID').last().reset_index()
        all_meter_ids = [1, 2, 3, 4, 5]
        display_data = []

        for mid in all_meter_ids:
            meter_row = latest_readings[latest_readings['Meter_ID'] == mid]
            audit_logger.info(f"Type of meter_row: {type(meter_row)}")
            if not meter_row.empty:
                audit_logger.info(f"Appending meter_row.iloc[0] of type {type(meter_row.iloc[0])}")
                display_data.append(meter_row.iloc[0])
            else:
                dummy_row = {'Meter_ID': mid, 'comm_status': 'FAILED', 'status': 'FAILED'}
                for param in main_params:
                    dummy_row[param] = "No data available"
                audit_logger.info(f"Appending dummy_row of type {type(dummy_row)}")
                display_data.append(pd.Series(dummy_row))
            audit_logger.info(f"Type of display_data after append: {type(display_data)}")


        connected_meters_df = pd.DataFrame(display_data)
        connected_meters_df = connected_meters_df.sort_values(by='Meter_ID').reset_index(drop=True)

        table_header = [html.Thead(html.Tr([html.Th("Meter Name", className="large-font"), html.Th("Meter ID", className="large-font"), html.Th("Status", className="large-font")] + [html.Th(param, className="large-font") for param in main_params]))]
        table_rows = []

        for index, row in connected_meters_df.iterrows():
            meter_id = row['Meter_ID']
            status = "Communication Failed" if row['comm_status'] == "FAILED" else row['status']
            status_color = "red" if status == "Communication Failed" else "yellow" if status == "POWER_FAIL" else "green"
            status_badge = dbc.Badge(status, color=RYB_COLORS[status_color], className="me-1 large-font", title=status)
            row_data = [html.Td(meter_names.get(meter_id, f"Unknown ({meter_id})"), className="large-font"), html.Td(meter_id, className="large-font"), html.Td(status_badge)]
            for param in main_params:
                value = row[param]
                row_data.append(html.Td(dbc.Badge(f"{value:.2f}" if isinstance(value, (int, float)) else str(value), color=RYB_COLORS['green'], className="me-1 large-font")))
            table_rows.append(html.Tr(row_data))

        table_body = [html.Tbody(table_rows)]
        return dbc.Table(table_header + table_body, bordered=True, hover=True, responsive=True, striped=True, className="table-sm")
    except Exception as e:
        audit_logger.error(f"Error in update_main_csv_data: {e}", exc_info=True)
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
        df_today = get_today_data(config['db_path'])
        if df_yesterday.empty and df_today.empty:
            audit_logger.warning("No DB data available for charts")
            return [px.line(title="No data available")] * 8 + [selected_meters]

        df_yesterday['DateTime'] = pd.to_datetime(df_yesterday['DateTime'], errors='coerce')
        df_today['DateTime'] = pd.to_datetime(df_today['DateTime'], errors='coerce')
        df_yesterday = df_yesterday[df_yesterday['Meter_ID'].isin(selected_meters)]
        df_today = df_today[df_today['Meter_ID'].isin(selected_meters)]

        color_sequence = [RYB_COLORS["red"], RYB_COLORS["yellow"], RYB_COLORS["blue"], RYB_COLORS["green"], RYB_COLORS["purple"]]
        chart_params = [
            ('VLL Average', 'VLL Average (Volts)', (0, 500)),
            ('Current Total', 'Current Total (Amps)', (0, 1000)),
            ('Watts Total', 'Watts Total (Watts)', (0, 1000000)),
            ('PF Average Received', 'PF Average Received', (0, 1))
        ]

        yesterday_figures = []
        today_figures = []

        yesterday_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        yesterday_end = yesterday_start + timedelta(days=1)
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        for param, ylabel, yrange in chart_params:
            fig_yesterday = px.line(
                df_yesterday, x='DateTime', y=param, color='Meter_ID',
                title=f'Yesterday: {param}',
                labels={'DateTime': 'Time', param: ylabel, 'Meter_ID': 'Meter'},
                color_discrete_sequence=color_sequence,
                hover_data={'Meter_ID': False, param: ':.2f', 'DateTime': '|%Y-%m-%d %H:%M:%S', 'Meter_Name': df_yesterday['Meter_ID'].map(meter_names) if not df_yesterday.empty else {}}
            )
            fig_yesterday.update_yaxes(range=yrange, gridcolor='lightgray')
            fig_yesterday.update_xaxes(showgrid=True, gridcolor='lightgray', range=[yesterday_start, yesterday_end])
            fig_yesterday.update_layout(hovermode='x unified')
            yesterday_figures.append(fig_yesterday)

            if df_today.empty:
                fig_today = px.line(title="No data available for Today")
            else:
                fig_today = px.line(
                    df_today, x='DateTime', y=param, color='Meter_ID',
                    title=f'Today: {param}',
                    labels={'DateTime': 'Time', param: ylabel, 'Meter_ID': 'Meter'},
                    color_discrete_sequence=color_sequence,
                    hover_data={'Meter_ID': False, param: ':.2f', 'DateTime': '|%Y-%m-%d %H:%M:%S', 'Meter_Name': df_today['Meter_ID'].map(meter_names) if not df_today.empty else {}}
                )
                fig_today.update_yaxes(range=yrange, gridcolor='lightgray')
                fig_today.update_xaxes(showgrid=True, gridcolor='lightgray', range=[today_start, today_end])
                fig_today.update_layout(hovermode='x unified')
            today_figures.append(fig_today)

        return yesterday_figures + today_figures + [selected_meters]
    except Exception as e:
        audit_logger.error(f"Error in update_db_charts: {e}")
        return [px.line(title=f"Error: {e}")] * 8 + [selected_meters]

@app.callback(
    Output('energy-consumption-layout', 'children'),
    [Input('interval-component-db', 'n_intervals')]
)
def update_energy_consumption_layout(n):
    try:
        # Calculate yesterday's date
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get energy consumption data
        yesterday_consumption = get_energy_consumption(config['db_path'], yesterday)
        today_consumption = get_energy_consumption(config['db_path'], today)
        
        # Create the beautiful layout
        return create_energy_consumption_layout(yesterday_consumption, today_consumption)
    except Exception as e:
        audit_logger.error(f"Error updating energy consumption layout: {e}")
        return html.Div(f"Error loading energy consumption data: {e}", className="text-center p-4")

@app.callback(
    [Output('collapse-yesterday-vll', 'is_open'),
     Output('collapse-yesterday-current', 'is_open'),
     Output('collapse-yesterday-watts', 'is_open'),
     Output('collapse-yesterday-pf', 'is_open'),
     Output('collapse-yesterday-button', 'children')],
    [Input('collapse-yesterday-button', 'n_clicks')],
    [State('collapse-yesterday-vll', 'is_open')]
)
def toggle_collapse_yesterday(n_clicks, is_open):
    try:
        if n_clicks:
            return not is_open, not is_open, not is_open, not is_open, "Show Yesterday's Charts" if is_open else "Hide Yesterday's Charts"
        return is_open, is_open, is_open, is_open, "Hide Yesterday's Charts" if is_open else "Show Yesterday's Charts"
    except Exception as e:
        audit_logger.error(f"Error in toggle_collapse_yesterday: {e}")
        return is_open, is_open, is_open, is_open, "Hide Yesterday's Charts" if is_open else "Show Yesterday's Charts"

@app.callback(
    [Output('collapse-today-vll', 'is_open'),
     Output('collapse-today-current', 'is_open'),
     Output('collapse-today-watts', 'is_open'),
     Output('collapse-today-pf', 'is_open'),
     Output('collapse-today-button', 'children')],
    [Input('collapse-today-button', 'n_clicks')],
    [State('collapse-today-vll', 'is_open')]
)
def toggle_collapse_today(n_clicks, is_open):
    try:
        if n_clicks:
            return not is_open, not is_open, not is_open, not is_open, "Show Today's Charts" if is_open else "Hide Today's Charts"
        return is_open, is_open, is_open, is_open, "Hide Today's Charts" if is_open else "Show Today's Charts"
    except Exception as e:
        audit_logger.error(f"Error in toggle_collapse_today: {e}")
        return is_open, is_open, is_open, is_open, "Hide Today's Charts" if is_open else "Show Today's Charts"

@app.callback(
    [Output('theme-store', 'data'),
     Output('main-container', 'style'),
     Output('main-navbar', 'dark'),
     Output('theme-toggle', 'value')],
    [Input('theme-toggle', 'value'),
     Input('url', 'pathname')],
    [State('theme-store', 'data')]
)
def manage_theme(toggle_value, pathname, stored_theme):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    if trigger_id == 'theme-toggle':
        new_theme = {'theme': 'dark' if toggle_value else 'light'}
    else:
        new_theme = stored_theme or {'theme': 'light'}
    
    if new_theme.get('theme') == 'dark':
        style = {'backgroundColor': RYB_COLORS['dark_bg'], 'color': RYB_COLORS['light_bg'], 'minHeight': '100vh'}
        navbar_dark = True
        toggle_value = True
    else:
        style = {'backgroundColor': RYB_COLORS['light_bg'], 'color': RYB_COLORS['dark_text'], 'minHeight': '100vh'}
        navbar_dark = False
        toggle_value = False
    
    return new_theme, style, navbar_dark, toggle_value

for meter_id in [1, 2, 3, 4, 5]:
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
            df = load_latest_csv_data()
            if df.empty:
                audit_logger.warning(f"No CSV data available for meter {current_meter_id} page update")
                return (html.Div(),) + ("0.00",) * 24

            meter_df = df[df['Meter_ID'] == current_meter_id].tail(1).reset_index()
            if meter_df.empty:
                audit_logger.warning(f"No data available for Meter ID {current_meter_id} after filtering")
                return (html.Div(),) + ("0.00",) * 24

            status = "Communication Failed" if meter_df.iloc[0]['comm_status'] == "FAILED" else meter_df.iloc[0]['status']
            if status in ['EB supply On', 'DG set On', 'OK']:
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050, use_reloader=False)