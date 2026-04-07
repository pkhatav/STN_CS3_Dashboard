import pandas as pd
import numpy as np
import os
import calendar
import dash
from dash import Dash, dash_table
from dash import dcc, html, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
from dash import callback_context
from dash import callback_context as ctx
from itertools import combinations
import plotly.io as pio
import warnings
warnings.filterwarnings("ignore")

'There are 3 main sections to this dashboard script. 1 - the filter_data function, 2 - the layout section, 3 - the table/plotting callbacks. Please see the instructions document for how these work.'

# === Global Loading ===

pio.templates.default = 'plotly_white' # Making the plots background white - feel free to change/delete
df_full = pd.read_csv('final_data.csv') # Script 01_producemergedcsv must be run first

# Created a function that filters the data to what is selected (to use in the plotting callbacks)
def filter_data(df, selected_variable, selected_months, selected_wyts, min_year, max_year, selected_units, dropna=True):
    
    '''
    This function filters the dataframe to the selected variables, months, and water year types, converts to the selected units, and drops columns & rows if they are entirely NaN (if specified).
    '''
    
    # Filtering to the selected variable
    df = df[df['Variable'] == selected_variable]

    # Creating a list of the columns which contain the values (these will be the historical, base, scenario value columns)
    model_columns = [col for col in df.columns if 'Value' in col]

    # Dropping NaN
    if dropna:
        df = df.dropna(how='all', subset=model_columns) # Drop any rows where all models have NaN values (for plotting purposes)
        df = df.dropna(axis=1, how='all') # Drop any models/columns (CalSim or historical) that have entirely NaN values
        model_columns = [col for col in df.columns if 'Value' in col] # Respecifying the columns which contain the values (in case some were dropped)

    # Filtering to the selected water years
    df = df[df['Water Year'].isin(np.arange(min_year, max_year + 1))]

    # Filtering to the selected months
    if not selected_months:
        selected_months = 'All' # If no months are selected that means we are using 'All' months (titling purposes)
    else:
        df = df[df['Month'].isin(selected_months)]

    # Filtering to the selected WYTs
    if not selected_wyts:
        selected_wyts = 'All'
    else:
        df_new_parts = []

        # For each selected WYT, loops through each model, makes a copy of the data equal to that value, and combines all the copies into one dataframe
        for selected_wyt in selected_wyts:  # i.e. SAC-C
            loc = selected_wyt.split('-')[0]  # SAC or SJV
            val = selected_wyt.split('-')[1]  # C, D, etc
            loc_cols = [c.replace('Value', f'WYT {loc}') for c in model_columns]  # (MODEL1) WYT SAC/SJR, (MODEL2) WYT SAC/SJR
            for loc_col in loc_cols:
                val_col = loc_col.replace(f'WYT {loc}', 'Value')  # (MODEL) Value

                # Sets the original dataframes values to NaN except for the model's selected WYT
                mask = df[loc_col].eq(val)
                df_wyt = df.copy()
                df_wyt[model_columns] = np.nan
                df_wyt[val_col] = df[val_col].where(mask)

                # Drops any rows where all models have NaN values
                df_wyt = df_wyt.dropna(subset=model_columns, how='all')
                df_new_parts.append(df_wyt)
        
        df = pd.concat(df_new_parts, ignore_index=True) # concats each model + selected WYT's new dataframe with NaN values in the other model's columns (there will be duplicate dates)
        df = df.drop_duplicates(subset=model_columns + ['Date'], keep='first').reset_index(drop=True) # drops any rows that have the exact same dates and values

        # Combines rows that have the same date by taking each of the model's values for that date and combining them into one row with no NaN values
        df = (
            df
            .sort_values("Date")
            .groupby("Date", as_index=False)
            .agg("first")
        )

    # Converting to the selected units
    if selected_units == 'cfs' and df['Units'].iloc[0] == 'taf':
        for col in model_columns:
            df[col] = (df[col])/(df['Date'].str.split('-').str[2].str.split(' ').str[0].astype(int) *24*60*60/(220*22*9*1000)) 
        df['Units'] = 'cfs'
        
    elif selected_units == 'taf' and df['Units'].iloc[0] == 'cfs':
        for col in model_columns:
            df[col] = (df[col]) * (df['Date'].str.split('-').str[2].str.split(' ').str[0].astype(int) *24*60*60/(220*22*9*1000))
        df['Units'] = 'taf'
    
    yaxis_title = df['Units'].iloc[0] if not df['Units'].empty else 'Value' # Plot's y-axis title will be the units

    return df, model_columns, selected_months, selected_wyts, yaxis_title

def create_excel_with_chart(df_input, excel_output, variable, x_axis, chart_title, chart_type, model_columns, months, wyts, min_year, max_year, yaxis_title):
    with pd.ExcelWriter(excel_output, engine="xlsxwriter") as writer:
        df_input.to_excel(writer, sheet_name="Sheet1", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]

        chart = workbook.add_chart({"type": chart_type})

        x_col = df_input.columns.get_loc(x_axis)

        for col in model_columns:
            col_num = df_input.columns.get_loc(col)

            chart.add_series({
                "name":       ["Sheet1", 0, col_num],
                "categories": ["Sheet1", 1, x_col, len(df_input), x_col],
                "values":     ["Sheet1", 1, col_num, len(df_input), col_num],
            })

        chart_title = f"{chart_title}- Months: {months}, Water Year Types: {wyts}, Water Years: {min_year}-{max_year}"

        chart.set_title({"name": chart_title})
        chart.set_x_axis({"name": x_axis})
        chart.set_y_axis({"name": yaxis_title})

        worksheet.insert_chart("E2", chart)

# WYT dropdown options
locs = ["SAC", "SJR"]
vals = ["W", "AN", "BN", "D", "C"]
    
# === Dash App ===

app = dash.Dash(__name__)

# === Layout ===

app.layout = html.Div([

    # Title
    html.H1('CalSim3 Model Post-Processing Dashboard', style={'textAlign': 'center', 'fontSize': '36px', 'fontWeight': 'bold', 'marginTop': '20px', 'marginBottom': '20px', 'fontFamily': 'Arial, sans-serif'}),

    # Kind dropdown
    html.Div([
        html.Div([
            html.P("Kind"),
            dcc.Dropdown(
                id='kind-dropdown',
                options=[{'label': k, 'value': k} for k in np.sort(df_full['Kind'].unique())], # The dropdown options will be all the unique 'Kind' values
                #value=np.sort(df_full['Kind'].unique())[0],
            )
        ], style={'flex': '1', 'width': '65%'}),

        # Variable dropdown
        html.Div([
            html.P("Variable"),
                dcc.Dropdown(
                    id='variable-dropdown', # Based on what 'Kind' is selected, the variable dropdown will be updated (see the first callback), if no 'Kind' is selected all variables will show
                )
        ], style={'flex': '1', 'width': '65%'}),

        # Months dropdown
        html.Div([
            html.P("Months"),
                dcc.Dropdown(
                    id='months-dropdown',
                    options=[{'label': m, 'value': m} for m in np.sort(df_full['Month'].unique())], # The dropdown options will be all the unique 'Month' values
                    multi=True, # Can select multiple
                )
        ], style={'flex': '1', 'width': '65%'}),

        # Water year type dropdown
        # The dropdown options will be all the unique WYT values (multiple columns), separating the name of the WYT and value with a dash (i.e. SAC-C)
        html.Div([
            html.P("Water Year Types"),
                dcc.Dropdown(
                    id='wyts-dropdown',
                    options = [{"label": f"{l} - {v}", "value": f"{l}-{v}"} for l in locs for v in vals], # The dropdown will show a space around the dash but the value outputted will not have that 
                    multi=True, # Can select multiple
                )
        ], style={'flex': '1', 'width': '65%'}),

        # Water years input
        html.Div([
            html.P("Water Years"),
            dcc.Input(
                id='min-year-input',
                type='number',
                placeholder='Min Year',
                value=df_full['Water Year'].min(), # Default value which will be updated once the variable is selected
                min=df_full['Water Year'].min(), # Minimum that can be selected
                max=df_full['Water Year'].max(), # Maximum that can be selected
                step=1, # Go up/down by 1 year
                style={'height': '22px', 'padding': '6px 12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'fontSize': '14px'}
            ),
            html.Span('-'), # Adds a dash between the min and max years input
            dcc.Input(
                id='max-year-input',
                type='number',
                placeholder='Max Year',
                value=df_full['Water Year'].max(),
                min=df_full['Water Year'].min(),
                max=df_full['Water Year'].max(),
                step=1,
                style={'height': '22px', 'padding': '6px 12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'fontSize': '14px'}
            )
        ], style={'flex': '0 1 auto'}),

        # Units selection
        html.Div([
            html.P('Units'),
            dcc.RadioItems(
                id='units-selected',
                options=[
                    {'label': 'TAF', 'value': 'taf'}, # The two options are TAF and CFS (the value outputted will be lowercase to match the data)
                    {'label': 'CFS', 'value': 'cfs'}
                ],
                value=None, # No default (unselected)
                inline=True,
                style={'height': '22px', 'padding': '6px 12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'fontSize': '14px'}
            )
            ], style={'flex': '0 1 auto'}),

        # Button to generate plots
        html.Div([
            html.P("Generate Plots"),
            html.Button("Click Here", id="plot-button", n_clicks=0, style={'height': '36px', 'padding': '6px 20px'}),
        ], style={'flex': '0 1 auto'}),

        # Button to download data 
        html.Div([
            html.P("Download Data"),
            html.Button("Click Here", id="download-button", n_clicks=0, style={'height': '36px', 'padding': '6px 20px'}),
            html.Div(id='dummy-output', style={'display': 'none'}) # Doesn't output anything, just downloads to a folder, so there is a dummy output
        ], style={'flex': '0 1 auto'}),
        
    ], style={'display': 'flex', 'gap': '10px'}),

    # Annual average table (styling the table)
    # There are separate ids for the table title and actual table
    html.Div([
        html.Div(id='table-title'),
        dash_table.DataTable(
            id='av-ann-table',
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left'},
            style_data={'color': 'black', 'backgroundColor': 'white'},
            style_header={'fontWeight': 'bold'}),
    ], style={'flex': '1', 'marginTop': '20px'}),

    # Historical data information table (styling the table)
    # There are separate ids for the table title and actual table
    html.Div([
        html.Div(id='hist-table-title'),
        dash_table.DataTable(
            id='constraint-source-table',
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left'},
            style_data={'color': 'black', 'backgroundColor': 'white'},
            style_cell_conditional=[{'if': {'column_id': 'Label'}, 'width': '420px',}]) # Adjusts the first columns width
    ], style={'flex': '1', 'marginTop': '20px'}),

    # Plots are in a 2x1 style (2 plots per row)
    # Monthly timeseries and averages
    html.Div([
        html.Div([
            dcc.Graph(id = 'monthly-timeseries'),
        ], style={'flex': '1'}),

         html.Div([
            dcc.Graph(id = 'monthly-averages'),
        ], style={'flex': '1'}),       
    
    ], style={'display': 'flex', 'gap': '10px'}),

    # Annual averages and exceedance plot
    html.Div([
        html.Div([
            dcc.Graph(id = 'annual-averages'),
        ], style={'flex': '1'}),
        
        html.Div([
            dcc.Graph(id = 'exceedance-plot'),
        ], style={'flex': '1'}),

    ], style={'display': 'flex', 'gap': '10px'}),

    # WYT barcharts
    html.Div([
        html.Div([
            dcc.Graph(id = 'wyt-index-sac'),
        ], style={'flex': '1'}),

        html.Div([
            dcc.Graph(id = 'wyt-index-sjr'),
        ], style={'flex': '1'}),
    
    ], style={'display': 'flex', 'gap': '10px'}),
    
])

# === Selection/Dropdown Callbacks ===

@app.callback(
    Output('kind-dropdown', 'options'),
    Output('kind-dropdown', 'value'),
    Output('variable-dropdown', 'options'),
    Output('variable-dropdown', 'value'),
    Input('kind-dropdown', 'value'),
    Input('variable-dropdown', 'value'),
)
def update_kind_variable_dropdowns(kind_value, variable_value):
    triggered = ctx.triggered_id
    all_kinds = sorted(df_full["Kind"].unique())
    all_kind_options = [{"label": k, "value": k} for k in all_kinds]
    all_variables = sorted(df_full["Variable"].unique())
    all_variable_options = [{"label": v, "value": v} for v in all_variables]

    # Changed 'Kind'
    if triggered == "kind-dropdown":
        if not kind_value:
            return (all_kind_options, None, all_variable_options, None)

        # Filter variables for selected kind
        filtered = df_full[df_full["Kind"] == kind_value]
        var_list = sorted(filtered["Variable"].unique())
        var_options = [{"label": v, "value": v} for v in var_list]

        # Update selected variable
        new_var = variable_value if variable_value in var_list else (var_list[0] if var_list else None)
        return (all_kind_options, kind_value, var_options, new_var)

    # Changed 'Variable'
    elif triggered == "variable-dropdown":
        if not variable_value:
            return (all_kind_options, None, all_variable_options, None)

        # Get the single kind for this variable (NOTE: THIS MIGHT NOT ALWAYS BE THE CASE, BUT IF THERE IS MORE THAN ONE IT'LL CAUSE OTHER ISSUES)
        kind = df_full.loc[df_full["Variable"] == variable_value, "Kind"].iloc[0]
        return (all_kind_options, kind,all_variable_options, variable_value)

    return (all_kind_options, None, all_variable_options, None)

@app.callback(
    Output('min-year-input', 'value'),
    Input('variable-dropdown', 'value')
)
def update_min_year_input(selected_variable):
    filtered_df = df_full[df_full['Variable'] == selected_variable] # Filters the data to the selected variable
    filtered_df = filtered_df.dropna(how='all', subset=[col for col in filtered_df.columns if 'Value' in col]) # The min year will be updated to match the min year of that variable
    value = filtered_df['Water Year'].min()
    return value

@app.callback(
    Output('max-year-input', 'value'),
    Input('variable-dropdown', 'value')
)
def update_max_year_input(selected_variable):
    filtered_df = df_full[df_full['Variable'] == selected_variable] # Filters the data to the selected variable
    filtered_df = filtered_df.dropna(how='all', subset=[col for col in filtered_df.columns if 'Value' in col]) # The min year will be updated to match the min year of that variable
    value = filtered_df['Water Year'].max()
    return value

# === Table and Plotting Callbacks ===

@app.callback(
    Output('table-title', 'children'),
    Output('av-ann-table', 'data'),
    Output('av-ann-table', 'columns'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def average_annual_table(n_clicks, variable, months, wyts, min_year, max_year, units):
    # Won't calculate unless the plot button is clicked
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return html.H4(), [], []

    df, model_columns, months, wyts, units = filter_data(
        df_full.copy(), variable, months, wyts, min_year, max_year, units, dropna=False
    )

    # Determine column label based on units
    if units.lower() == "cfs":
        avg_label = f"Average ({units})"
    else:
        avg_label = f"Annual Average ({units})"

    # Create an empty table with these columns
    df_table = pd.DataFrame(columns=[
        'Study',
        avg_label,
        'Abs Diff from Historical',
        '% Diff from Historical',
        'Abs Diff from Base',
        '% Diff from Base'
    ])

    # Multiply flows by 1 (cfs) or volumes by 12
    factor = 1 if units.lower() == "cfs" else 12

    # Calculate the annual average of all the studies and save it with the name and value
    annual_averages = {}
    for col in model_columns:
        study_name = col.replace(' Value', '')
        annual_avg = df[col].mean() * factor
        annual_averages[study_name] = annual_avg

    hist_study_name = [name for name in annual_averages if "Historical" in name][0]
    hist_avg = annual_averages[hist_study_name]
    base_study_name = [name for name in annual_averages if "Base" in name][0]
    base_avg = annual_averages[base_study_name]

    # Calculate the absolute and percent difference from historical or base
    for study_name, annual_avg in annual_averages.items():

        hist_diff = None
        hist_percent_diff = None
        base_diff = None
        base_percent_diff = None

        # Calculate differences from historical
        if study_name != hist_study_name:
            hist_diff = abs(annual_avg - hist_avg)
            hist_mid = (annual_avg + hist_avg) / 2
            hist_percent_diff = (hist_diff / hist_mid) * 100

        # Calculate differences from base
        if study_name != base_study_name:
            base_diff = abs(annual_avg - base_avg)
            base_mid = (annual_avg + base_avg) / 2
            base_percent_diff = (base_diff / base_mid) * 100

        # Fill in the table and only show 2 decimal places
        df_table.loc[len(df_table)] = {
            'Study': study_name,
            avg_label: f"{annual_avg:.2f}",
            'Abs Diff from Historical': f"{hist_diff:.2f}" if hist_diff is not None else None,
            '% Diff from Historical': f"{hist_percent_diff:.2f}%" if hist_percent_diff is not None else None,
            'Abs Diff from Base': f"{base_diff:.2f}" if base_diff is not None else None,
            '% Diff from Base': f"{base_percent_diff:.2f}%" if base_percent_diff is not None else None
        }

    # These need to be returned to create the table
    table_title = html.H4('Annual Average Values', style={'fontFamily': 'Arial, sans-serif'})
    data = df_table.to_dict('records')
    columns = [{"name": i, "id": i} for i in df_table.columns]

    return table_title, data, columns

@app.callback(
    Output('hist-table-title', 'children'),
    Output('constraint-source-table', 'data'),
    Output('constraint-source-table', 'columns'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def hist_constraint_source(n_clicks, variable, months, wyts, min_year, max_year, units):
    # Won't calculate unless the plot button is clicked
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return html.H4(), [], []

    df, model_columns, months, wyts, units = filter_data(df_full.copy(), variable, months, wyts, min_year, max_year, units, dropna=False) # Calling the function defined earlier

    # Get the historical dates, constraint, and data source to put into a table
    beg_date = df['Historical Beg. Date'].dropna().iloc[0] if not df['Historical Beg. Date'].dropna().empty else np.nan # If any of these are empty it will be NaN in the table
    end_date = df['Historical End Date'].dropna().iloc[0] if not df['Historical End Date'].dropna().empty else np.nan
    constraint = df['Historical Constraint'].dropna().iloc[0] if not df['Historical Constraint'].dropna().empty else np.nan
    source = df['Historical Source'].dropna().iloc[0] if not df['Historical Source'].dropna().empty else np.nan

    # Add rows for the historical dates, constraint, and data source 
    hist_df = pd.DataFrame([
        ['Historical Beg. Date:', beg_date],
        ['Historical End Date:', end_date],
        ["Used as a historical data constraint in CS3HIST?", constraint],
        ["Data source:", source]
    ], columns=['Label', 'Value'])

    # These need to be returned to create the table
    hist_table_title = html.H4('Historical Data Information', style={'fontFamily': 'Arial, sans-serif'}) # Print this out above table
    data = hist_df.to_dict('records')
    columns = [{'name': '', 'id': 'Label'}, {'name': '', 'id': 'Value'}] # Remove column names

    return hist_table_title, data, columns

@app.callback(
    Output('monthly-timeseries', 'figure'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def plot_monthly_timeseries(n_clicks, variable, months, wyts, min_year, max_year, units):
    # Won't plot unless the plot button is clicked
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return {}

    df, model_columns, months, wyts, yaxis_title = filter_data(df_full.copy(), variable, None, None, min_year, max_year, units) # The monthly timeseries will not filter with months or wyts

    fig = go.Figure()

    # The raw data is plotted
    for col in model_columns:
        study_name = col.replace(' Value', '')
        fig.add_trace(go.Scattergl(x=df['Date'], y=df[col], mode='lines', name=study_name, hovertemplate='%{x}, %{y:.2f}')) # the y-value will only show 2 decimal places when hovered
    
    fig.update_layout(
        title=f"<span style='font-size:20px'><b>{variable} Monthly Time Series</b></span><br><span style='font-size:14px'>Months: {months}, Water Year Types: {wyts}, Water Years: {min_year}-{max_year}</span>",
        xaxis_title='Date',
        yaxis_title=yaxis_title,
        legend_title='Study'
    )
    return fig

@app.callback(
    Output('monthly-averages', 'figure'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def plot_monthly_averages(n_clicks, variable, months, wyts, min_year, max_year, units):
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return {}
        
    df, model_columns, months, wyts, yaxis_title = filter_data(df_full.copy(), variable, months, wyts, min_year, max_year, units)

    # Group by the month and take the average
    df_grouped = df.groupby('Month')[model_columns].mean().reset_index()
    df_grouped['Month Name'] = df_grouped['Month'].apply(lambda x: calendar.month_name[int(x)]) # Apply the tranformation to turn into month names instead of numbers (for the x-axis)

    # Plot the months from October to September
    month_order = ['October', 'November', 'December', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September']
    df_grouped['Month Name'] = pd.Categorical(df_grouped['Month Name'], categories=month_order, ordered=True)
    df_grouped = df_grouped.sort_values('Month Name')

    mode = 'markers' if months != 'All' else 'lines' # If months are selected it will become a scatter plot instead of line
    
    fig = go.Figure()

    for col in model_columns:
        study_name = col.replace(' Value', '')
        fig.add_trace(go.Scatter(x=df_grouped['Month Name'], y=df_grouped[col], mode=mode, name=study_name, hovertemplate='%{x}, %{y:.2f}'))
    
    fig.update_layout(
        title=f"<span style='font-size:20px'><b>{variable} Monthly Averages</b></span><br><span style='font-size:14px'>Months: {months}, Water Year Types: {wyts}, Water Years: {min_year}-{max_year}</span>",
        xaxis_title='Month',
        yaxis_title=yaxis_title,
        legend_title='Study'
    )
    return fig

@app.callback(
    Output('annual-averages', 'figure'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def plot_annual_averages(n_clicks, variable, months, wyts, min_year, max_year, units):
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return {}

    df, model_columns, months, wyts, yaxis_title = filter_data(df_full.copy(), variable, months, wyts, min_year, max_year, units)

    # Group by the water year and take the average
    df_grouped = df.groupby('Water Year')[model_columns].mean().reset_index()
    
    fig = go.Figure()

    for col in model_columns:
        study_name = col.replace(' Value', '')
        df_grouped[col] = df_grouped[col] * 12 # Multiply by 12 to get the annual average
        fig.add_trace(go.Scatter(x=df_grouped['Water Year'], y=df_grouped[col], mode='lines+markers', name=study_name, hovertemplate='%{x}, %{y:.2f}'))
    
    fig.update_layout(
        title=f"<span style='font-size:20px'><b>{variable} Annual Averages</b></span><br><span style='font-size:14px'>Months: {months}, Water Year Types: {wyts}, Water Years: {min_year}-{max_year}</span>",
        xaxis_title='Water Year',
        yaxis_title=yaxis_title,
        legend_title='Study'
    )
    
    return fig

@app.callback(
    Output('exceedance-plot', 'figure'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def plot_monthly_exceedances(n_clicks, variable, months, wyts, min_year, max_year, units):
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return {}

    df, model_columns, months, wyts, yaxis_title = filter_data(df_full.copy(), variable, months, wyts, min_year, max_year, units)

    fig = go.Figure()

    # Calculate exceedances (ignores NaN values)
    for col in model_columns:
        study_name = col.replace(' Value', '')
        values = df[col].dropna().sort_values(ascending=False).reset_index(drop=True) # Sort descending
        exceedance = values.rank(method='first', ascending=False) / (len(values) + 1) # Exceedance formula
        fig.add_trace(go.Scatter(x=exceedance, y=values, mode='lines', name=study_name, hovertemplate='%{x:.2f}, %{y:.2f}'))
    
    fig.update_layout(
        title=f"<span style='font-size:20px'><b>{variable} Monthly Exceedance</b></span><br><span style='font-size:14px'>Months: {months}, Water Year Types: {wyts}, Water Years: {min_year}-{max_year}</span>",
        xaxis_title='Exceedance Probability',
        yaxis_title=yaxis_title,
        legend_title='Study'
    )
    return fig

@app.callback(
    Output('wyt-index-sac', 'figure'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def plot_wyt_sac(n_clicks, variable, months, wyts, min_year, max_year, units):
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return {}

    df, model_columns, months, wyts, yaxis_title = filter_data(df_full, variable, months, wyts, min_year, max_year, units)
    df_avg, model_columns_avg, months_avg, wyts_avg, yaxis_title_avg = filter_data(df_full, variable, None, None, min_year, max_year, units) # The average bar won't filter for months or WYTs

    wyt_order = ['W', 'AN', 'BN', 'D', 'C']
    wyt_columns = [col for col in df.columns if 'WYT SAC' in col]
    
    fig = go.Figure()

    if not wyt_columns: # If there are no WYTs (not sure how) or they are all empty, it will skip
        pass
    
    else:
        # Creates a dictionary of dataframes for each study grouped by their respective WYT column 
        grouped_df = {
            col: df.groupby(col.replace('Value', 'WYT SAC'))[col].mean().reset_index()
            for col in model_columns
        }
        
        # Creates a dataframe with the WYT and average value for each model_column
        for col in model_columns:
            wyt_col = col.replace('Value', 'WYT SAC')
            df_grouped = grouped_df[col] # Calls the dataframe from the dictionary
            df_grouped = df_grouped.set_index(wyt_col).reindex(wyt_order).reset_index() # Reorders the data to match the wyt_order (wet to dry)
            df_grouped[col] = df_grouped[col].apply(lambda x: None if pd.isna(x) else x) # If there isn't a value for a WYT, it will become None
            
            avg_val = df_avg[col].mean() # The average bar takes the mean of all the data
    
            # Since there is more than one WYT, it will take that column from the dataframe as the x-axis, and the values for the y-axis
            x_vals = list(df_grouped[wyt_col]) + ['Overall Average<br>(All Months & WYTs)']
            y_vals = list(df_grouped[col]) + [avg_val]
            text_vals = [f"{val:.2f}" if val is not None else "None" for val in y_vals] # Shows 2 decimal places in the text inside the bars
            
            study_name = col.replace(' Value', '')
    
            fig.add_trace(go.Bar(x=x_vals, y=y_vals, name=study_name, text=text_vals, textposition='inside', hovertemplate='%{x}, %{y:.3f}'))

    fig.update_layout(
        title=f"<span style='font-size:20px'><b>{variable} Sacramento Valley Index Average</b></span><br><span style='font-size:14px'>Months: {months}, Water Year Types: {wyts}, Water Years: {min_year}-{max_year}</span>",
        xaxis_title='Water Year Type',
        yaxis_title=yaxis_title,
        legend_title='Study'
    )
    return fig

@app.callback(
    Output('wyt-index-sjr', 'figure'),
    Input('plot-button', 'n_clicks'),
    Input('variable-dropdown', 'value'),
    Input('months-dropdown', 'value'),
    Input('wyts-dropdown', 'value'),
    Input('min-year-input', 'value'),
    Input('max-year-input', 'value'),
    Input('units-selected', 'value')
)
def plot_wyt_sjr(n_clicks, variable, months, wyts, min_year, max_year, units):
    ctx = callback_context
    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] != 'plot-button':
        return {}

    df, model_columns, months, wyts, yaxis_title = filter_data(df_full, variable, months, wyts, min_year, max_year, units)
    df_avg, model_columns_avg, months_avg, wyts_avg, yaxis_title_avg = filter_data(df_full, variable, None, None, min_year, max_year, units)

    wyt_order = ['W', 'AN', 'BN', 'D', 'C']
    wyt_columns = [col for col in df.columns if 'WYT SJR' in col]
    
    fig = go.Figure()
    
    if not wyt_columns: # If there are no WYTs (not sure how) or they are all empty, it will skip
        pass
    
    else: 
        # Creates a dictionary of dataframes for each study grouped by their respective WYT column 
        grouped_df = {
            col: df.groupby(col.replace('Value', 'WYT SJR'))[col].mean().reset_index()
            for col in model_columns
        }
        
        # Creates a dataframe with the WYT and average value for each model_column
        for col in model_columns:
            wyt_col = col.replace('Value', 'WYT SJR')
            df_grouped = grouped_df[col] # Calls the dataframe from the dictionary
            df_grouped = df_grouped.set_index(wyt_col).reindex(wyt_order).reset_index() # Reorders the data to match the wyt_order (wet to dry)
            df_grouped[col] = df_grouped[col].apply(lambda x: None if pd.isna(x) else x) # If there isn't a value for a WYT, it will become None
            
            avg_val = df_avg[col].mean() # The average bar takes the mean of all the data

            # Since there is more than one WYT, it will take that column from the dataframe as the x-axis, and the values for the y-axis
            x_vals = list(df_grouped[wyt_col]) + ['Overall Average<br>(All Months & WYTs)']
            y_vals = list(df_grouped[col]) + [avg_val]
            text_vals = [f"{val:.2f}" if val is not None else "None" for val in y_vals] # Shows 2 decimal places in the text inside the bars
            
            study_name = col.replace(' Value', '')
    
            fig.add_trace(go.Bar(x=x_vals, y=y_vals, name=study_name, text=text_vals, textposition='inside', hovertemplate='%{x}, %{y:.3f}'))
    
    fig.update_layout(
        title=f"<span style='font-size:20px'><b>{variable} San Joaquin Valley Index Average</b></span><br><span style='font-size:14px'>Months: {months}, Water Year Types: {wyts}, Water Years: {min_year}-{max_year}</span>",
        xaxis_title='Water Year Type',
        yaxis_title=yaxis_title,
        legend_title='Study'
    )
    return fig

@app.callback(
    Output('dummy-output', 'children'),
    Input('download-button', 'n_clicks'),
    State('variable-dropdown', 'value'),
    State('months-dropdown', 'value'),
    State('wyts-dropdown', 'value'),
    State('min-year-input', 'value'),
    State('max-year-input', 'value'),
    State('units-selected', 'value')
)
def download_data(n_clicks, variable, months, wyts, min_year, max_year, units):
    
    '''
    This function will run if the download button is clicked on the dashboard. It loops through the various plots and saves their data as CSVs (repeating the same calculations), rounded to 3 decimals.

    Potential changes: I can change this to download to your computer instead of the downloaded_data folder. I can also change the download names in the future to include variable name and other params.
    '''

    # Won't download data unless the button is pressed
    if n_clicks == 0:
        raise dash.exceptions.PreventUpdate

    # Make sure the downloaded_data folder exists, if not, create it
    if not os.path.exists('downloaded_data'):
        os.makedirs('downloaded_data')

    df, model_columns, months_na, wyts, units = filter_data(df_full.copy(), variable, months, wyts, min_year, max_year, units, dropna=False)

    df = df.drop(columns=['Historical Beg. Date', 'Historical End Date', 'Historical Constraint', 'Historical Source'])

    df.round(3).to_csv('downloaded_data/monthly_timeseries.csv', index=False)
    create_excel_with_chart(df, 'downloaded_data/monthly_timeseries_chart.xlsx', variable, 'Date', f'{variable} Monthly Timeseries', 'line', model_columns, months_na, wyts, min_year, max_year, units)

    df_grouped = df.groupby('Month')[model_columns].mean().reset_index()
    df_grouped.round(3).to_csv('downloaded_data/monthly_averages.csv', index=False)
    create_excel_with_chart(df_grouped, 'downloaded_data/monthly_averages_chart.xlsx', variable, 'Month', f'{variable} Monthly Averages', 'line', model_columns, months_na, wyts, min_year, max_year, units)
    
    df_grouped = df.groupby('Water Year')[model_columns].mean().reset_index()
    for col in model_columns:
        df_grouped[col] = df_grouped[col] * 12
    df_grouped.round(3).to_csv('downloaded_data/annual_averages.csv', index=False)
    create_excel_with_chart(df_grouped, 'downloaded_data/annual_averages_chart.xlsx', variable, 'Water Year', f'{variable} Annual Averages', 'line', model_columns, months_na, wyts, min_year, max_year, units)

    exceedance_df = pd.DataFrame()
    for col in model_columns:
        study_name = col.replace(' Value', '')
        values = df[col].dropna().sort_values(ascending=False).reset_index(drop=True)
        exceedance = values.rank(method='first', ascending=False) / (len(values) + 1)
        exceedance_df[col] = values  
        exceedance_df[f"{study_name} Exceedance"] = exceedance  
    exceedance_df.round(3).to_csv("downloaded_data/monthly_exceedance_probabilities.csv", index=False)

    # Drop the NaN rows and columns for the WYT to work
    df = df.dropna(how='all', subset=model_columns) 
    df = df.dropna(axis=1, how='all')
    
    model_columns = [col for col in df.columns if 'Value' in col] 

    wyt_order = ['W', 'AN', 'BN', 'D', 'C']
    sac_df_grouped = pd.DataFrame({'WYT': wyt_order})
    sjr_df_grouped = pd.DataFrame({'WYT': wyt_order})
    wyt_sac_columns = [col for col in df.columns if 'WYT SAC' in col]
    wyt_sjr_columns = [col for col in df.columns if 'WYT SJR' in col]

    wyt_columns = [col for col in df.columns if 'WYT' in col]
    
    if not wyt_columns: # If there are no WYTs (not sure how) or they are all empty, it will skip
        pass
    
    else:
        for col in model_columns:
            wyt_sac_col = col.replace('Value', 'WYT SAC')
            sac_avg = df.groupby(wyt_sac_col)[col].mean().reset_index()
            sac_df = sac_avg.set_index(wyt_sac_col).reindex(wyt_order).reset_index()
            sac_df[col] = sac_df[col].apply(lambda x: None if pd.isna(x) else x)
            sac_df_grouped = pd.concat([sac_df_grouped, sac_df[[col]]], axis=1)
    
            wyt_sjr_col = col.replace('Value', 'WYT SJR')
            sjr_avg = df.groupby(wyt_sjr_col)[col].mean().reset_index()
            sjr_df = sjr_avg.set_index(wyt_sjr_col).reindex(wyt_order).reset_index()
            sjr_df[col] = sjr_df[col].apply(lambda x: None if pd.isna(x) else x)
            sjr_df_grouped = pd.concat([sjr_df_grouped, sjr_df[[col]]], axis=1)
            
        sac_df_grouped.round(3).to_csv('downloaded_data/sacramento_wyt_averages.csv', index=False)
        sjr_df_grouped.round(3).to_csv('downloaded_data/san_joaquin_wyt_averages.csv', index=False)
            
        create_excel_with_chart(sac_df_grouped, 'downloaded_data/sacramento_wyt_averages_chart.xlsx', variable, 'WYT', f'{variable} Sacramento Valley Index Average', 'column', model_columns, months_na, wyts, min_year, max_year, units)
        create_excel_with_chart(sjr_df_grouped, 'downloaded_data/san_joaquin_wyt_averages_chart.xlsx', variable, 'WYT', f'{variable} San Joaquin Valley Index Average', 'column', model_columns, months_na, wyts, min_year, max_year, units)
    
if __name__ == '__main__':
    app.run(debug=True)
