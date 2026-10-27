import csv
import pandas as pd
import os
from datetime import datetime
import numpy as np

# Folder where favorite exports are
EXPORT_DIR = "data/WEAP_Favorites_Exports"

# Files to include that don't have an ObjID (made to -999)
FILES_WITHOUT_OBJID = {
    'Theoretical_Catchment_Irrigation_Demand.csv'
}

def print_rows_below_given_row(csv_file, given_row=4):
    # Read in data as lines and convert to dataframe
    with open(csv_file, 'r', newline='') as f:
        rows = list(csv.reader(f))

    units = rows[given_row-2][0]
    favorite = rows[given_row-4][0]
    header = rows[given_row-1]
    data = rows[given_row:]
    variable_col = header[1]

    df = pd.DataFrame(data, columns=header)

    df['Units'] = units # add units column
    df['WEAP Favorite'] = favorite # add favorites column

    # Theoretical demands don't have ObjIDs
    if csv_file in [os.path.join(EXPORT_DIR, file) for file in FILES_WITHOUT_OBJID]:
        variable_col = header[0] # branch
        df['ObjID'] = -999
    else:
        variable_col = header[1] # normal WEAP variable column

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
    df_long = df_long.rename(
        columns={
            variable_col: "WEAP Variable",
            "Date": "Date_Time",
            "Units": "WEAP Units"
        }
    )

    df_long = df_long.sort_values(["WEAP Variable", "Date_Time"])

    # ObjID formatting
    df_long['ObjID'] = df_long['ObjID'].astype(str).str.strip().astype(int)

    # Unit corrections/consistent formatting
    df_long['Value'] = pd.to_numeric(
        df_long['Value'],
        errors='coerce'
    )

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

def add_calculated_data(df):

    def aggregate_by_du(data):
        # Sum Value, keep first for every other column
        agg_dict = {
            col: ('sum' if col == 'Value' else 'first')
            for col in data.columns
            if col not in ['Date_Time', 'DU']
        }
        return data.groupby(['Date_Time', 'DU'], as_index=False).agg(agg_dict)

    # Rename DUs to sum together
    du_renames = {
        'A_61N_NA1': 'A_61_NA1',
        'A_61S_NA1': 'A_61_NA1',
    
        'A_61N_NA4.1': 'A_61_NA4',
        'A_61N_NA4.2': 'A_61_NA4',
        'A_61N_NA4.3': 'A_61_NA4',
        'A_61S_NA4.1': 'A_61_NA4',
        'A_61S_NA4.2': 'A_61_NA4',
    
        'A_61N_PA3': 'A_61_PA3',
        'A_61S_NA6': 'A_61_PA3',
    
        'A_62_NA6.1': 'A_62_NA6',
        'A_62_NA6.2': 'A_62_NA6',
        'A_62_NA7': 'A_62_NA6',

        'A_63_NA3.1': 'A_63_NA3_1', # converted to 63_NA3 in mapping
        'A_63_NA3.2': 'A_63_NA3_2', # converted to 63_NA5 in mapping
    
        'A_63_NA5': 'A_63_NA4',
        'A_63_NA4': 'A_63_NA4',
    
        'A_64_NA2.1': 'A_64_NA2',
        'A_64_NA2.2': 'A_64_NA2',
        'A_64_NA2.3': 'A_64_NA2',
        'A_64_NA3.1': 'A_64_NA2',
        'A_64_NA3.2': 'A_64_NA2',
        'A_64_NA3.3': 'A_64_NA2',
        'A_64_NA4': 'A_64_NA2',
    }

    # Sum all groundwater pumping variables for each DU
    gp_df = df[df['WEAP Favorite'] == 'Transmission Link Flow'].copy()
    gp_df = gp_df[gp_df['WEAP Variable'].str.contains(r'GW to U_|GW to A_|GW to R_', na=False)].copy()
    gp_df['DU'] = gp_df['WEAP Variable'].str.split('GW to', n=1).str[1].str.strip()
    
    gp_df['DU'] = gp_df['DU'].replace(du_renames)
    gp_df['DU'] = gp_df['DU'].str.split('.').str[0].str.strip()
    gp_df['DU'] = gp_df['DU'].str.replace(r'^(U_(?:62|63|64|71|72)_NU)\d+$',r'\1',regex=True) # If 62, 63, 64, 71, 72_NU{#}, sum and make it _NU
    gp_df = aggregate_by_du(gp_df)

    # Replace WEAP Variable with the calculated GP variable
    gp_df['WEAP Variable'] = 'GP_' + gp_df['DU']
    gp_df['ObjID'] = -999 # Give a synthetic ObjID
    gp_df = gp_df.drop(columns='DU')

    # Sum all demand variables for each DU
    aw_df = df[df['WEAP Favorite'] == 'Theoretical Catchment Irrigation Demand'].copy()
    aw_df['DU'] = aw_df['WEAP Variable'].str.strip()
    aw_df['Mapped'] = aw_df['DU'].isin(du_renames)
    aw_df['DU'] = aw_df['DU'].replace(du_renames)
    aw_df['DU'] = aw_df['DU'].str.split('.').str[0].str.strip()

    # Only append calculated rows that are summed
    aw_df = aw_df.groupby(['Date_Time', 'DU']).filter(lambda x: x['Mapped'].any() or len(x) > 1)
    aw_df = aw_df.drop(columns='Mapped')
    aw_df = aggregate_by_du(aw_df)

    # Replace WEAP Variable with the calculated AW variable
    aw_df['WEAP Variable'] = aw_df['DU']
    aw_df['ObjID'] = -999 # Give a synthetic ObjID
    aw_df = aw_df.drop(columns='DU')

    # Concat
    return pd.concat([df, gp_df, aw_df], ignore_index=True)

def create_weap_csv():
    '''
    This function creates a temporary WEAP CSV file from the CSVs in the WEAP_Favorites_Exports folder, which will then be converted to CalSim formatting.
    It only uses the CSVs listed in the WEAP Favorites tab of dashboard_name_mapping.xlsx that have month columns and ObjIDs. 
    '''
    
    csv_list_file = pd.read_excel('input_files/dashboard_name_mapping.xlsx', sheet_name='WEAP Favorites', usecols=['CalSim Kind','WEAP Favorite Name','CSV File','WEAP Location'])
    csv_list_file = csv_list_file.dropna()['CSV File'].to_list() # edit to only include certain files

    # Filter to specific CSVs
    csv_files = [
        file_path
        for csv_file in csv_list_file
        for file_path in [os.path.join(EXPORT_DIR, str(csv_file).strip())]
        if file_path.endswith(".csv")
        and os.path.exists(file_path)
        and (has_month_columns_and_objid(file_path) # function above
             or file_path in [os.path.join(EXPORT_DIR, file) for file in FILES_WITHOUT_OBJID]
            ) 
    ]
    
    all_dfs = [
        print_rows_below_given_row(csv_file, given_row=4) # function above
        for csv_file in csv_files
    ]
    
    final_df = pd.concat(all_dfs, ignore_index=True)

    # Append GP_ variables (function above)
    final_df = add_calculated_data(final_df)
    
    final_df.to_csv('input_files/WEAP_CalSim/WEAP_file_tmp.csv', index=False)

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
    calsim_weap_map = pd.read_excel(
        'input_files/dashboard_name_mapping.xlsx',
        sheet_name='Final',
        usecols=[
            'CalSim Variable',
            'CalSim Kind',
            'ObjID',
            'WEAP Variable',
            'WEAP Model',
            'WEAP Favorite'
        ]
    )
    calsim_weap_map = calsim_weap_map.dropna().drop_duplicates()
    calsim_weap_map = calsim_weap_map[
        calsim_weap_map['WEAP Model'].str.lower() == weap_model.lower()
    ]
    calsim_weap_map['ObjID'] = calsim_weap_map['ObjID'].astype(int)

    # Read in the WEAP data and merge CalSim variable name and kind
    # Only keep WEAP data that has a CalSim equivalent
    weap_file = pd.read_csv('input_files/WEAP_CalSim/WEAP_file_tmp.csv')

    # WEAP variables with ObjID: match using ObjID + WEAP Favorite
    real_df = weap_file[weap_file['ObjID'] != -999].merge(
        calsim_weap_map[
            ['ObjID', 'WEAP Favorite', 'WEAP Variable',
             'CalSim Variable', 'CalSim Kind']
        ],
        on=['ObjID', 'WEAP Favorite'],
        suffixes=['_after', '_before']
    )
    
    # WEAP variables without ObjID or synthetic variables: match using WEAP Variable + WEAP Favorite
    synthetic_df = weap_file[weap_file['ObjID'] == -999].merge(
        calsim_weap_map[
            ['WEAP Favorite', 'WEAP Variable',
             'CalSim Variable', 'CalSim Kind']
        ],
        on=['WEAP Favorite', 'WEAP Variable']
    )
    
    # Concat
    df = pd.concat(
        [real_df, synthetic_df],
        ignore_index=True
    )
    
    df = df.sort_values(['CalSim Variable', 'Date_Time'])

    # Print out any WEAP variable names that were changed
    df_mismatch = df[df['WEAP Variable_before'] != df['WEAP Variable_after']].groupby('ObjID').first()[['WEAP Variable_after', 'WEAP Variable_before']]
    
    print("List of WEAP variable names that were changed:")
    for _, row in df_mismatch.iterrows():
        print(f"{row['WEAP Variable_before']} --> {row['WEAP Variable_after']}")
    # Save mismatch as CSV?

    ### TBD: HOW TO PRINT OUT OBJID + WEAP VARIABLE NAME CHANGES

    # Drop and rename columns to get to CalSim format
    df = df[['WEAP Units', 'Date_Time', 'CalSim Variable', 'CalSim Kind', 'Value']] # in WEAP units
    df = df.rename(columns={"WEAP Units":"Units","CalSim Variable":"Variable","CalSim Kind":"Kind"})
    df = df.drop_duplicates()

    # Convert to CalSim units
    df['Date_Time'] = pd.to_datetime(df['Date_Time'])

    kind_mask = (
        df['Kind'].str.lower().str.contains(
            'applied-water|channel|delivery|diversion|evaporation|flow|gw-pumping|inflow|return-flow|river-spills',
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