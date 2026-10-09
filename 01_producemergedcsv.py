import os
import pandas as pd
import numpy as np
import ast
from pathlib import Path
import csv
from datetime import datetime
from input_files.DSS_CSV_Converter.DSS_CSV_Convert import convert_to_csv
from input_files.WEAP_CalSim.WEAP_FavExp import *
from input_files.WEAP_CalSim.WEAP_to_CalSim import *

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

SAC_WYT_CSV = 'data/WEAP_Favorites_Exports/Sac_WYT.csv'
SJR_WYT_CSV = 'data/WEAP_Favorites_Exports/SJR_WYT.csv'

def update_input(input_file):
    """
    Add the historical-data CSV into the input file (if present & missing)
    Convert any .DSS input files to CSV using the appropriate FV file
    Exports any WEAP favorites and converts into CSV in data folder
    Add the hist WYT data to the models if they are hist models
    """
    input_file = Path(input_file)
    txt = pd.read_csv(input_file)

    hist_data = str(HIST_CSV_PATH)

    historical_data = {
        'Model Name': 'Historical Data',
        'File Location or WEAP Area': hist_data,
        'Type': 'Historical',
        'Study': 'Historical'
    }

    # Add historical row if file exists and input list doesn't already have it
    if HIST_CSV_PATH.exists():
        file_loc_list = txt['File Location or WEAP Area'].astype(str).str.strip().tolist() if 'File Location or WEAP Area' in txt.columns else []
        if hist_data not in file_loc_list:
            final_txt = pd.concat([txt, pd.DataFrame([historical_data])], ignore_index=True)
        else:
            final_txt = txt.copy()
    else:
        final_txt = txt.copy()
    
    # Convert any .dss entries to .csv 
    for idx, row in final_txt.iterrows():
        f = str(row['File Location or WEAP Area']).strip()
        if f.lower().endswith(".dss"):
            fv_type = str(row.get('Study', '')).strip().lower()
            fv_file = FV_HIST if fv_type == 'historical' else FV_PLAN
            convert_to_csv(f, fv_file)
            final_txt.loc[idx, 'File Location or WEAP Area'] = f[:-4] + ".csv"

    # Export WEAP models to .csv (see input_files/WEAP_CalSim for more info)
    for idx, row in final_txt.iterrows():
        if (
            str(row.get('Study', '')).strip().lower() in {'sacwam', 'sjwam'}
            and not str(row.get('File Location or WEAP Area', '')).strip().lower().endswith('.csv')
        ):
            weap_area = str(row['File Location or WEAP Area']).strip()
            weap_model = str(row['Study']).strip().lower()
            output_file = "data/" + weap_area + ".csv"
            if os.path.exists(output_file): # if this weap export already exists, it won't re-export it
                print(
                f"WEAP output CSV file already exists, skipping export and using existing file:\n"
                f" {output_file}\n"
                f"If you would like to create a new CSV, rename or delete the existing CSV file, then rerun this script."
                )
                continue
            export_weap_favorites(weap_area) # exports weap favorites from the model, must have weap open
            create_weap_csv() # creates csv from specific favorite files
            save_as_calsim_format(output_file, weap_model, SJR_WYT_CSV, SAC_WYT_CSV) # saves the csv in calsim format (maps variables)
            final_txt.loc[idx, 'File Location or WEAP Area'] = output_file

    # Add hist WYT data if the model is a historical model
    hist_df = None
    if HIST_CSV_PATH.exists():
        hist_df = pd.read_csv(HIST_CSV_PATH, **READ_KW)
    
    for idx, row in final_txt.iterrows():
        if (
            hist_df is not None
            and str(row.get('Study', '')).strip().lower() in {'historical'} 
        ):
            f = str(row['File Location or WEAP Area']).strip()
    
            # Skip the historical data source file itself
            if Path(f).resolve() == HIST_CSV_PATH.resolve():
                continue
    
            df = pd.read_csv(f, **READ_KW)
    
            existing_vars = set(df['Variable'].astype(str).str.strip())
    
            # Only add if neither WYT variable is already present
            if not {'WYT_SAC_', 'WYT_SJR_'}.issubset(existing_vars):
    
                wyt_rows = hist_df.loc[
                    hist_df['Variable'].isin(['WYT_SAC_', 'WYT_SJR_']),
                    ['Date_Time', 'Variable', 'Value']
                ]

                wyt_rows['Kind'] = 'wateryeartype'
                wyt_rows['Units'] = 'none'
    
                df = pd.concat([df, wyt_rows], ignore_index=True) # sets any missing columns to NaN
                df.to_csv(f, index=False)

    final_txt.to_csv(input_file, index=False)

def add_val_variables(input_file):
    """
    For each CSV listed in input_file, compute validation variables
    defined in input_files/val_variables.csv and append them to each CSV.
    Skips the validation variable if any of the variables to sum are missing.
    """

    new_vars = pd.read_csv("input_files/val_variables.csv")

    parsed_definitions = []

    # Build validation variables
    for row_number, vrow in new_vars.iterrows():
        variables_to_sum = ast.literal_eval(str(vrow["variables_to_sum"]))
        coefficients = ast.literal_eval(str(vrow["coefficients"]))

        parsed_definitions.append(
            {
                "variable_name": vrow["variable_name"],
                "kind": vrow["kind"],
                "variables_to_sum": list(variables_to_sum),
                "coefficients": list(coefficients),
            }
        )

    txt = pd.read_csv(input_file)

    for _, file_row in txt.iterrows():
        f = str(file_row['File Location or WEAP Area']).strip()
        df = pd.read_csv(f, **READ_KW)

        # Ensure Value is numeric
        df["Value"] = pd.to_numeric(df["Value"], errors="coerce")

        # Normalize Units
        df["Units"] = (df["Units"].astype("string").str.lower().str.strip())

        # Calculate c once for every original row
        # Using the day of month from Date_Time
        day = df["Date_Time"].dt.day.fillna(1).astype(int)
        df["c"] = (day * 24 * 60 * 60 / (220 * 22 * 9 * 1000))

        variable_lookup = {
            variable: group.copy()
            for variable, group in df.groupby(
                "Variable",
                sort=False,
                dropna=False,
            )
        }

        existing_vars = set(variable_lookup)

        # Store new rows and concatenate once
        appended_dfs = []

        for definition in parsed_definitions:
            variable_name = definition["variable_name"]
            kind = definition["kind"]
            variables_to_sum = definition["variables_to_sum"]
            coefficients = definition["coefficients"]

            # Skip if validation variable already exists in the df
            if variable_name in existing_vars:
                continue

            # Skip if any required variable to sum is missing
            missing_vars = [
                variable
                for variable in variables_to_sum
                if variable not in existing_vars
            ]

            if missing_vars:
                continue

            # Check for duplicate Date_Time values within each variable
            duplicate_inputs = []

            for variable in variables_to_sum:
                variable_df = variable_lookup[variable]

                duplicate_mask = variable_df["Date_Time"].duplicated(keep=False)

                if duplicate_mask.any():
                    duplicate_inputs.append(variable)

            if duplicate_inputs:
                print(
                    f"Skipping validation variable {variable_name}: duplicate Date_Time "
                    f"values found for {duplicate_inputs}"
                )
                continue

            base_var = variables_to_sum[0]

            # Keep all metadata from the first/base variable
            df_final = (
                variable_lookup[base_var]
                .copy()
                .set_index("Date_Time", drop=False)
            )

            # Find dates shared by every variable
            common_dates = df_final.index

            for variable in variables_to_sum[1:]:
                variable_dates = pd.Index(
                    variable_lookup[variable]["Date_Time"]
                )

                common_dates = common_dates.intersection(
                    variable_dates,
                    sort=False,
                )

            if len(common_dates) == 0:
                continue

            # Retain only shared dates
            df_final = df_final.loc[common_dates].copy()

            # Start calculated result at zero
            calculated_value = pd.Series(
                0.0,
                index=df_final.index,
                dtype="float64",
            )

            uses_c = False

            # Add each variable to sum
            for variable, coefficient in zip(
                variables_to_sum,
                coefficients,
            ):
                source = (
                    variable_lookup[variable]
                    .set_index("Date_Time")
                    .loc[common_dates]
                )
                
                source_value = source["Value"].astype(float)

                if isinstance(coefficient, str):
                    coefficient = coefficient.strip()

                if coefficient == "c":
                    calculated_value = (
                        calculated_value
                        + source_value * source["c"]
                    )
                    uses_c = True
                else:
                    numeric_coefficient = float(coefficient)
                    calculated_value = (
                        calculated_value
                        + source_value * numeric_coefficient
                    )

            if calculated_value is None:
                continue

            df_final["Value"] = calculated_value
            df_final["Kind"] = kind
            df_final["Variable"] = variable_name

            for column in [
                "Historical Constraint",
                "Historical Source",
            ]:
                if column in df_final.columns:
                    df_final[column] = np.nan

            if uses_c:
                df_final["Units"] = "taf"

            df_final.reset_index(drop=True, inplace=True)

            appended_dfs.append(df_final)

            # Add the new validation variable to the lookup
            variable_lookup[variable_name] = df_final.copy()
            existing_vars.add(variable_name)

        if appended_dfs:
            df = pd.concat(
                [df, *appended_dfs],
                ignore_index=True,
                sort=False,
            )

        df.drop(columns=["c"], inplace=True, errors="ignore")
        df.to_csv(f, index=False)


def filter_and_merge_csvs(input_file):
    """
    Merge all model CSVs listed in input_file into one wide table.
    - Keeps rows with keys (Variable, Date_Time, Kind, Units)
    - Renames each model's Value column to '{Type}: {Model Name} Value'
    - Adds Water Year and Month
    - Adds per-model WYT SAC/SJR via MAP
    """
    txt = pd.read_csv(input_file)

    chunk_size = 10_000_000
    merged_chunks = []

    # First model setup
    first_model_name = txt.loc[0, 'Model Name']
    first_file = str(txt.loc[0, 'File Location or WEAP Area']).strip()
    first_type_run = txt.loc[0, 'Type']
    first_model_label = f"{first_type_run}: {first_model_name}"

    # Preload & normalize other models once
    other_models = []
    for _, row in txt.iloc[1:].iterrows():
        model_label = f"{row['Type']}: {row['Model Name']}"
        file_path = str(row['File Location or WEAP Area']).strip()
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

    # Prepare WYT mappings (Date -> per-model WYT value)
    model_val_cols = [c for c in merged_df.columns if c.endswith(' Value')]

    # Build SAC map
    if (merged_df['Variable'] == 'WYT_SAC_').any():
        wyt_sac = (
            merged_df.loc[
                merged_df['Variable'] == 'WYT_SAC_',
                ['Date'] + model_val_cols
            ]
            .groupby('Date', as_index=True)
            .first()
        )
    else:
        wyt_sac = None

    # Build SJR map
    if (merged_df['Variable'] == 'WYT_SJR_').any():
        wyt_sjr = (
            merged_df.loc[
                merged_df['Variable'] == 'WYT_SJR_',
                ['Date'] + model_val_cols
            ]
            .groupby('Date', as_index=True)
            .first()
        )
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
