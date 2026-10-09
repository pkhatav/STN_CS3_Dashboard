import csv
import pandas as pd
import os
from datetime import datetime
import numpy as np

def print_rows_below_given_row(csv_file, given_row=4):
    # Read in data as lines and convert to dataframe
    with open(csv_file, 'r', newline='') as f:
        rows = list(csv.reader(f))

    units = rows[given_row-2][0] # where units are located in CSV
    favorite = rows[given_row-4][0] # where the variable is coming from on weap
    header = rows[given_row-1] # actual header row
    data = rows[given_row:]    # rows with data
    variable_col = header[1]   # variable names

    df = pd.DataFrame(data, columns=header)
    
    df['Units'] = units # add units column
    df['WEAP Favorite'] = favorite # add favorites column

    # Melt/transpose the dataframe to have the date and values as rows
    # ObjID, variable, units, and favorite as columns
    df_long = df.melt(
        id_vars=['ObjID', variable_col, 'Units', 'WEAP Favorite'],
        var_name='Date',
        value_name='Value'
    )

    # Match CalSim date formatting
    df_long['Date'] = (
        pd.to_datetime(df_long['Date'], format='%b %Y')
        + pd.offsets.MonthEnd(0)
    )

    # Additional formatting
    df_long = df_long.rename(columns={variable_col:"WEAP Variable","Date":"Date_Time","Units":"WEAP Units"})
    df_long = df_long.sort_values(["WEAP Variable", "Date_Time"])
    df_long['ObjID'] = df_long['ObjID'].astype(str).str.strip().astype(int)

    # Unit corrections/consistent formatting
    df_long['Value'] = pd.to_numeric(df_long['Value'], errors='coerce')
    
    mask = df_long['WEAP Units'].eq('Acre-foot') # AF to TAF
    df_long.loc[mask, 'Value'] /= 1000
    df_long.loc[mask, 'WEAP Units'] = 'taf'
    
    df_long['WEAP Units'] = df_long['WEAP Units'].replace({
        'Thousand Acre Feet': 'taf',
        'Cubic Feet per Second': 'cfs'
    })

    return df_long

def has_month_columns_and_objid(csv_file, header_row=3):
    with open(csv_file, 'r', newline='') as f:
        rows = list(csv.reader(f))

    # Check if the CSV file has variables with ObjIDs
    header = [col.strip() for col in rows[header_row]]
    has_objid = "ObjID" in header

    # Check if the CSV file has months as the columns
    has_month = False
    for col in header:
        try:
            datetime.strptime(col, '%b %Y')
            has_month = True
            break
        except ValueError:
            pass

    return has_objid and has_month # only use CSVs that have these

def create_weap_csv():
    '''
    This function creates a temporary WEAP CSV file from the CSVs in the WEAP_Favorites_Exports folder, which will then be converted to CalSim formatting.
    It only uses the CSVs listed in the WEAP Favorites tab of dashboard_name_mapping.xlsx that have month columns and ObjIDs. 
    '''
    
    # Folder where favorite exports are
    export_dir = "data/WEAP_Favorites_Exports"
    
    csv_list_file = pd.read_excel('input_files/dashboard_name_mapping.xlsx', sheet_name='WEAP Favorites')
    csv_list_file = csv_list_file.dropna()['CSV File'].to_list() # edit to only include certain files

    # Filter to specific CSVs
    csv_files = [
        file_path
        for csv_file in csv_list_file
        for file_path in [os.path.join(export_dir, str(csv_file).strip())]
        if file_path.endswith(".csv")
        and os.path.exists(file_path)
        and has_month_columns_and_objid(file_path) # function above
    ]
    
    all_dfs = [
        print_rows_below_given_row(csv_file, given_row=4) # function above
        for csv_file in csv_files
    ]
    
    final_df = pd.concat(all_dfs, ignore_index=True)
    
    final_df.to_csv('input_files/WEAP_CalSim/WEAP_file_tmp.csv', index=False)

def make_weap_match_key(series):
    # Creates a version of the WEAP variable that doesn't include any numbers
    match_key = series.astype('string').str.strip()

    # Keep the number when the slash is followed by "Reach"
    is_reach = match_key.str.contains(
        r'\\\s*Reach\b$',
        case=False,
        regex=True,
        na=False
    )

    # Otherwise, remove the number immediately before the slash
    match_key.loc[~is_reach] = (
        match_key.loc[~is_reach]
        .str.replace(r'\s*\d+\s*(?=\\)', '', regex=True)
        .str.replace(r'\s+', ' ', regex=True)
        .str.strip()
    )

    return match_key

def add_wyt_data(weap_model, SJR_WYT_CSV, SAC_WYT_CSV, given_row=3):
    # Creates a dataframe with the SJ or Sac WYT data, depending on the model
    if weap_model.lower() == 'sjwam':
        csv_file = SJR_WYT_CSV
    elif weap_model.lower() == 'sacwam':
        csv_file = SAC_WYT_CSV

    if not os.path.exists(csv_file):
        raise FileNotFoundError(
            "PLEASE ADD WYT FAVORITE TO WEAP (named Sac WYT or SJR WYT)"
        )

    with open(csv_file, 'r', newline='') as f:
        rows = list(csv.reader(f))

    header = rows[given_row]
    data = rows[given_row + 1:]

    df = pd.DataFrame(data, columns=header)
    df = df.T.reset_index()[1:].rename(columns={'index':'Date_Time', 0:'Value'})

    if weap_model.lower() == 'sjwam':
        df['Variable'] = 'WYT_SJR_'
    elif weap_model.lower() == 'sacwam':
        df['Variable'] = 'WYT_SAC_'

    df['Kind'] = 'wateryeartype'
    df['Units'] = 'none'

    df = df[['Units','Date_Time','Variable','Kind','Value']]

    df['Date_Time'] = (
        pd.to_datetime(df['Date_Time'], format='%b %Y')
        + pd.offsets.MonthEnd(0)
    )
    
    return df

def save_as_calsim_format(output_file, weap_model, SJR_WYT_CSV, SAC_WYT_CSV):
    '''
    This function takes in the WEAP_file_tmp.csv created and saves it in CalSim format in the data folder.
    It only keeps data that has a CalSim equivalent from the mapping file.
    It appends the Sac or SJ WYT data from the WEAP model (SJRR_WYT and Sac WYT OctSep variables).
    Additionally, it prints out any WEAP variable names that were changed.
    '''

    # Filter map to SacWAM or SJWAM
    calsim_weap_map = pd.read_excel('input_files/dashboard_name_mapping.xlsx', sheet_name='Final')
    calsim_weap_map = calsim_weap_map.dropna()
    calsim_weap_map = calsim_weap_map[
        calsim_weap_map['WEAP Model'].str.lower() == weap_model.lower()
    ]
    calsim_weap_map['ObjID'] = calsim_weap_map['ObjID'].astype(int)

    # Read in the WEAP data and merge CalSim variable name and kind
    # Only keep WEAP data that has a CalSim equivalent
    weap_file = pd.read_csv('input_files/WEAP_CalSim/WEAP_file_tmp.csv')

    # Function above
    calsim_weap_map['_weap_match_key'] = make_weap_match_key(
        calsim_weap_map['WEAP Variable']
    )
    
    weap_file['_weap_match_key'] = make_weap_match_key(
        weap_file['WEAP Variable']
    )

    # Merge on ObjID, match key, and WEAP Favorite
    df = weap_file.merge(
        calsim_weap_map[['ObjID', '_weap_match_key', 'WEAP Favorite', 'WEAP Variable', 'CalSim Variable', 'CalSim Kind']],
        on=['ObjID', '_weap_match_key', 'WEAP Favorite'],
        suffixes=['_after', '_before']
    )
    df = df.sort_values(['CalSim Variable', 'Date_Time'])

    # Print out any WEAP variable names that were changed
    df_mismatch = df[df['WEAP Variable_before'] != df['WEAP Variable_after']].groupby('ObjID').first()[['WEAP Variable_after', 'WEAP Variable_before']]
    
    print("List of WEAP variable names that were changed:")
    for _, row in df_mismatch.iterrows():
        print(f"{row['WEAP Variable_before']} --> {row['WEAP Variable_after']}")
    # Save mismatch as CSV?

    '''
    # DEBUG TO CHECK IF OBJIDS CHANGE
    debug = weap_file.merge(
        calsim_weap_map[['ObjID', '_weap_match_key', 'WEAP Favorite', 'WEAP Variable']],
        on=['_weap_match_key', 'WEAP Favorite'],
        how='inner',
        suffixes=['_after', '_before']
    )
    
    objid_changes = debug[debug['ObjID_before'] != debug['ObjID_after']]

    for _, row in objid_changes.iterrows():
        print(f"ObjID {row['ObjID_before']} --> {row['ObjID_after']}")
        print(f"{row['WEAP Variable_before']} --> {row['WEAP Variable_after']}")
    '''

    # Drop and rename columns to get to CalSim format
    df = df[['WEAP Units', 'Date_Time', 'CalSim Variable', 'CalSim Kind', 'Value']] # in WEAP units
    df = df.rename(columns={"WEAP Units":"Units","CalSim Variable":"Variable","CalSim Kind":"Kind"})
    df = df.drop_duplicates()

    # Convert to CalSim units
    df['Date_Time'] = pd.to_datetime(df['Date_Time'])

    kind_mask = (
        df['Kind'].str.lower().str.contains(
            'channel|diversion|evaporation|flow|inflow|return-flow|river-spills',
            na=False
        )
        &
        (df['Units'].str.lower() == 'taf')
    )
    
    days = df['Date_Time'].dt.days_in_month
    
    factor = days * 24 * 60 * 60 / (220 * 22 * 9 * 1000)
    
    df.loc[kind_mask, 'Value'] = (
        df.loc[kind_mask, 'Value']
        / factor[kind_mask]
    )
    
    df.loc[kind_mask, 'Units'] = 'cfs'

    df['Kind'] = df['Kind'].str.lower()

    # Append WYT data to the dataframe
    df_wyt = add_wyt_data(weap_model, SJR_WYT_CSV, SAC_WYT_CSV) # function above
    df = pd.concat([df, df_wyt], ignore_index=True)

    df.to_csv(output_file, index=False) # save to data folder as the name specified in the input.txt file