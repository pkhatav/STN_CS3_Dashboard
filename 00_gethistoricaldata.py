import pandas as pd
import numpy as np
import os

def get_historical_data(excel_file):
    
    '''
    This function will take in an Excel file (excel_file), read the sheet named "CS3HIST DivData MekongV1.2", and create a CSV file in the data folder in a similar formatting to the CalSim files.

    Excel file format: 23 rows, 3 extra columns, dates in the fourth, NaN values equal to -2.
    
    Issue: This will not work on Excel files that do not follow the same format above.
    '''
    
    # Formatting
    df = pd.read_excel(excel_file, sheet_name='CS3HIST DivData MekongV1.2', header=list(range(23))) # Must have the sheet name "CS3HIST DivData MekongV1.2" and 23 rows of headers
    df = df.iloc[:, 3:] # Drop the first three columns
    dates = df.columns[0] # The fourth column must have the dates (now first column)
    
    df = df.loc[:, ~df.columns.get_level_values(5).str.contains('Unnamed')] # Drop any columns that do not have a variable name
    df = df.replace(-2, np.nan) # NaN values must equal -2
    
    # Create empty dataframe with the columns the final dataframe will be
    columns = ['Units', 'Date_Time', 'Variable', 'Kind', 'Value', 'Historical Beg. Date', 'Historical End Date', 'Historical Constraint', 'Historical Source']
    historical_df = pd.DataFrame(columns=columns)
    
    # Make sure the dates are in the same format as CalSim, YYYY:MM:DD 00:00:000
    date = df[dates].astype(str) + ' 00:00:00'
    
    # Loop through each column, fill in the dataframe, and for certain kinds convert the units from TAF to CFS to match CalSim data
    for col in df.columns[1:]: # Ignore the first column (dates)
        kind = col[df.columns[0].index('Dashboard Kind')] #  Kind must be in row 'Dashboard Kind'
        units = col[df.columns[0].index('Units:')].strip().lower() # Units Units must be in row 'Units'
        beg_date = col[df.columns[0].index('Historical Beg. Date:')]
        end_date = col[df.columns[0].index('Historical End Date:')]
        constraint = col[df.columns[0].index('Included SV?')] # Used as a historical data constraint must be in row 'Included SV?'
        source = np.nan if 'Unnamed' in col[df.columns[0].index('WRESL Code Comment')] else col[df.columns[0].index('WRESL Code Comment')] # Data source must be in row 'WRESL Code Comment', NaN if there is no source
        
        if 'channel' in kind and units == 'taf': # Checks if units are in TAF first before converting
            units = 'cfs'
            variable = col[df.columns[0].index('Name')] # The variable name must be in row 'Name'
            value = (df[col])/(date.str.split('-').str[2].str.split(' ').str[0].astype(int) *24*60*60/(220*22*9*1000))
        elif ('diversion' in kind or 'cs3_hist' in kind) and units == 'taf':
            units = 'cfs'
            variable = col[df.columns[0].index('Name')]
            value = (df[col])/(date.str.split('-').str[2].str.split(' ').str[0].astype(int) *24*60*60/(220*22*9*1000))
        elif 'evaporation' in kind and units == 'taf':
            units = 'cfs'
            variable = col[df.columns[0].index('Name')]
            value = (df[col])/(date.str.split('-').str[2].str.split(' ').str[0].astype(int) *24*60*60/(220*22*9*1000))
        elif 'return_flow' in kind and units == 'taf':
            units = 'cfs'
            variable = col[df.columns[0].index('Name')]
            value = (df[col])/(date.str.split('-').str[2].str.split(' ').str[0].astype(int) *24*60*60/(220*22*9*1000))
        elif 'river_spills' in kind and units == 'taf':
            units = 'cfs'
            variable = col[df.columns[0].index('Name')]
            value = (df[col])/(date.str.split('-').str[2].str.split(' ').str[0].astype(int) *24*60*60/(220*22*9*1000))
        else:
            units = col[df.columns[0].index('Units:')].strip().lower()
            variable = col[df.columns[0].index('Name')]
            value = df[col]
        
        temp_df = pd.DataFrame({
            'Units': units,
            'Date_Time': date,
            'Variable': variable,
            'Kind': kind,
            'Value': value,
            'Historical Beg. Date': beg_date,
            'Historical End Date': end_date,
            'Historical Constraint': constraint,
            'Historical Source': source
        })
        
        historical_df = pd.concat([historical_df, temp_df], ignore_index=True)

    # Make sure values are numeric
    historical_df['Value'] = pd.to_numeric(historical_df['Value'], errors='coerce')

    # Make sure the data folder exists, if not, create it
    if not os.path.exists('data'):
        os.makedirs('data')
    historical_df.to_csv('data/historical_data.csv', index=False)

if __name__ == "__main__":
    get_historical_data('input_files/historical_data.xlsx')
