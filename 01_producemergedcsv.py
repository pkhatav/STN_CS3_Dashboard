import os
import pandas as pd
import numpy as np
import ast
from pathlib import Path
from input_files.DSS_CSV_Converter.DSS_CSV_Convert import convert_to_csv

# ---- Common read options to stop DtypeWarning and speed things up ----
# We only keep the columns we actually need.
USECOLS = ['Variable', 'Date_Time', 'Kind', 'Units', 'Value',
           'id', 'PartA', 'PartF', 'Timestep',            # may exist; will drop
           'Historical Beg. Date', 'Historical End Date', # may exist; won't drop
           'Historical Constraint', 'Historical Source']  # may exist; won't drop

DTYPES = {
    'Variable': 'string',
    'Kind': 'string',
    'Units': 'string'
    # 'Value' -> we coerce to numeric after reading
}

READ_KW = dict(
    dtype=DTYPES,
    usecols=lambda c: c in USECOLS or c in ['Variable','Date_Time','Kind','Units','Value'],
    parse_dates=['Date_Time'],
    # infer_datetime_format=True, # removed in my pandas version
    low_memory=False
)

HIST_CSV_PATH = Path("data/historical_data.csv")
FV_HIST = "input_files/fv/hist_model_variables.fv"
FV_PLAN = "input_files/fv/planning_model_variables.fv"


def update_input(input_file):
    """
    Add the historical-data CSV into the input file (if present & missing)
    and convert any .DSS input files to CSV using the appropriate FV file.
    """
    input_file = Path(input_file)
    txt = pd.read_csv(input_file)

    hist_data = str(HIST_CSV_PATH)

    historical_data = {
        'Model Name': 'Historical Data',
        'File Location': hist_data,
        'Type': 'Historical',
        'Historical or Planning Model': 'Historical'
    }

    # Add historical row if file exists and input list doesn't already have it
    if HIST_CSV_PATH.exists():
        file_loc_list = txt['File Location'].astype(str).str.strip().tolist() if 'File Location' in txt.columns else []
        if hist_data not in file_loc_list:
            final_txt = pd.concat([txt, pd.DataFrame([historical_data])], ignore_index=True)
        else:
            final_txt = txt.copy()
    else:
        final_txt = txt.copy()

    # Convert any .dss entries to .csv (not expected for your current 3-CSV case, but kept for robustness)
    for idx, row in final_txt.iterrows():
        f = str(row['File Location']).strip()
        if f.lower().endswith(".dss"):
            fv_type = str(row.get('Historical or Planning Model', '')).strip().lower()
            fv_file = FV_HIST if fv_type == 'historical' else FV_PLAN
            convert_to_csv(f, fv_file)
            final_txt.loc[idx, 'File Location'] = f[:-4] + ".csv"

    final_txt.to_csv(input_file, index=False)


def add_val_variables(input_file):
    """
    For each CSV listed in input_file, compute validation variables
    defined in input_files/val_variables.csv and append them to each CSV.
    """
    new_vars = pd.read_csv('input_files/val_variables.csv')
    txt = pd.read_csv(input_file)

    for _, row in txt.iterrows():
        f = str(row['File Location']).strip()
        df = pd.read_csv(f, **READ_KW)

        # Coerce numeric after read
        df['Value'] = pd.to_numeric(df['Value'], errors='coerce')

        # Normalize Units
        df['Units'] = df['Units'].str.lower().str.strip()

        # Conversion factor c (kept as you had it, but using parsed datetime)
        # Using the day of month from Date_Time
        day = df['Date_Time'].dt.day.fillna(1).astype(int)
        df['c'] = day * 24 * 60 * 60 / (220 * 22 * 9 * 1000)  # consider naming the denominator constant

        # Build validation variables
        for __, vrow in new_vars.iterrows():
            try:
                variables_to_sum = ast.literal_eval(vrow['variables_to_sum'])
                coefficients = ast.literal_eval(vrow['coefficients'])
            except Exception:
                continue

            variable_name = vrow['variable_name']
            kind = vrow['kind']

            # Skip if already present
            if 'Variable' in df.columns and variable_name in df['Variable'].unique():
                continue

            # Base var
            base_var = variables_to_sum[0]
            base_coef = coefficients[0]
            df_final = df[df['Variable'] == base_var].copy().reset_index(drop=True)
            if df_final.empty:
                continue

            df_final['Value'] = df_final['Value'] * (df_final['c'] if base_coef == 'c' else int(base_coef))

            # Sum the rest
            for var, coef in zip(variables_to_sum[1:], coefficients[1:]):
                temp_df = df[df['Variable'] == var].copy().reset_index(drop=True)
                if temp_df.empty:
                    continue
                temp_df['Value'] = temp_df['Value'] * (temp_df['c'] if coef == 'c' else int(coef))
                # Align by index (dates are aligned because we filtered per variable)
                df_final['Value'] = df_final['Value'] + temp_df['Value']

            df_final['Kind'] = kind
            df_final['Variable'] = variable_name

            # Null historical-only fields if they exist
            for col in ['Historical Constraint', 'Historical Source']:
                if col in df_final.columns:
                    df_final[col] = np.nan

            if 'c' in coefficients:
                df_final['Units'] = 'taf'

            df = pd.concat([df, df_final], ignore_index=True)

        # Clean up & save
        df.drop(columns='c', inplace=True)
        df.to_csv(f, index=False)


def filter_and_merge_csvs(input_file):
    """
    Merge all model CSVs listed in input_file into one wide table.
    - Keeps rows with keys (Variable, Date_Time, Kind, Units)
    - Renames each model's Value column to '{Type}: {Model Name} Value'
    - Adds Water Year and Month
    - Adds per-model WYT SAC/SJR via MAP (no row multiplication)
    """
    txt = pd.read_csv(input_file)

    chunk_size = 10_000_000
    merged_chunks = []

    # First model setup
    first_model_name = txt.loc[0, 'Model Name']
    first_file = str(txt.loc[0, 'File Location']).strip()
    first_type_run = txt.loc[0, 'Type']
    first_model_label = f"{first_type_run}: {first_model_name}"

    # Preload & normalize other models once
    other_models = []
    for _, row in txt.iloc[1:].iterrows():
        model_label = f"{row['Type']}: {row['Model Name']}"
        file_path = str(row['File Location']).strip()
        other_df = pd.read_csv(file_path, **READ_KW)
        other_df['Value'] = pd.to_numeric(other_df['Value'], errors='coerce')
        other_df['Units'] = other_df['Units'].str.lower().str.strip()
        other_df = other_df.drop(columns=['id', 'PartA', 'PartF', 'Timestep'], errors='ignore')
        other_df.rename(columns={'Value': f"{model_label} Value"}, inplace=True)
        other_models.append(other_df)

    # Read first model in chunks (for very large files)
    for chunk in pd.read_csv(first_file, chunksize=chunk_size, **READ_KW):
        chunk['Value'] = pd.to_numeric(chunk['Value'], errors='coerce')
        chunk['Units'] = chunk['Units'].str.lower().str.strip()
        chunk = chunk.drop(columns=['id', 'PartA', 'PartF', 'Timestep'], errors='ignore')
        chunk.rename(columns={'Value': f"{first_model_label} Value"}, inplace=True)

        # Merge others
        for other_df in other_models:
            chunk = chunk.merge(other_df, on=['Variable', 'Date_Time', 'Kind', 'Units'], how='outer')

        merged_chunks.append(chunk)

    merged_df = pd.concat(merged_chunks, ignore_index=True)

    # Normalize date & convenience columns
    merged_df.rename(columns={'Date_Time': 'Date'}, inplace=True)
    merged_df['Date'] = pd.to_datetime(merged_df['Date'], errors='coerce')
    merged_df['Month'] = merged_df['Date'].dt.month
    year = merged_df['Date'].dt.year
    merged_df['Water Year'] = year + merged_df['Month'].isin([10, 11, 12]).astype(int)

    final_df = merged_df.copy()

    # Prepare WYT mappings (Date -> per-model WYT value) without row multiplication
    model_val_cols = [c for c in merged_df.columns if c.endswith(' Value')]

    # Build SAC map
    if (merged_df['Variable'] == 'WYT_SAC_').any():
        wyt_sac = (merged_df.loc[merged_df['Variable'] == 'WYT_SAC_', ['Date'] + model_val_cols]
                   .drop_duplicates('Date').set_index('Date'))
    else:
        wyt_sac = None

    # Build SJR map
    if (merged_df['Variable'] == 'WYT_SJR_').any():
        wyt_sjr = (merged_df.loc[merged_df['Variable'] == 'WYT_SJR_', ['Date'] + model_val_cols]
                   .drop_duplicates('Date').set_index('Date'))
    else:
        wyt_sjr = None

    # Map WYT values
    for col in model_val_cols:
        if wyt_sac is not None:
            final_df[col.replace(' Value', ' WYT SAC')] = final_df['Date'].map(wyt_sac[col])
        if wyt_sjr is not None:
            final_df[col.replace(' Value', ' WYT SJR')] = final_df['Date'].map(wyt_sjr[col])

    # Map numeric WYT -> categories
    wyt_columns = [c for c in final_df.columns if 'WYT' in c]
    final_df[wyt_columns] = final_df[wyt_columns].replace({1: 'W', 2: 'AN', 3: 'BN', 4: 'D', 5: 'C'})

    # Optional memory hygiene
    for c in ['Variable', 'Kind', 'Units']:
        if c in final_df.columns:
            final_df[c] = final_df[c].astype('category')

    final_df = final_df.set_index('Variable')
    final_df.to_csv('final_data.csv')


if __name__ == "__main__":
    update_input("input_files/input.txt")
    add_val_variables("input_files/input.txt")
    filter_and_merge_csvs("input_files/input.txt")
