
import os
import pandas as pd
from pydsstools.heclib.dss import HecDss
import numpy as np

def convert_to_csv(file_location, fv_file):
    # Input DSS file and CSV file
    input_DSS = file_location
    Output_Path_File = fv_file
    startDate = "1NOV1921"
    endDate = "1OCT2021"
    study_ID = 0
    
    # Open DSS file
    src_dss = HecDss.Open(input_DSS)
    
    # Read the CSV file and extract 'Part B' column
    df = pd.read_csv(Output_Path_File)
    part_b_column = df['Part B']
    
    # Output CSV file
    output_csv = file_location.replace('.dss', '.csv')
    
    # Header line
    line_1 = "id,Timestep,Units,Date_Time,Variable,Kind,Value"
    
    # Open output file and write header
    with open(output_csv, 'w') as f_out:
        f_out.write(line_1 + '\n')
    
        # Iterate through each value in Part B column
        for value in part_b_column:
            pathname_pattern = f"/*/{value}/*/*/*/*/"
            paths = src_dss.getPathnameList(pathname_pattern, sort=True)
            if not paths:
                continue
            path = paths[0]
            path_parts = path.split('/')
            path_parts[4] = f"{startDate} - {endDate}"
            full_path = '/'.join(path_parts)
    
            # Read time series data
            ts = src_dss.read_ts(
                full_path,
                window=("31OCT1921 00:00:00","30SEP2021 00:00:00"),
                trim_missing=True
            )
            
            times = np.array(ts.pytimes)
            values = ts.values
            units = ts.units.lower()
            timestep = ts.interval
            kind = path_parts[3].lower()

            # Subtract a day to match CS3 formatting
            times = pd.to_datetime(times, format="%m/%d/%Y %H:%M", errors="coerce")
            times = times - pd.Timedelta(days=1)
            is_feb29 = (times.month == 2) & (times.day == 29)
            times = times.where(~is_feb29, times - pd.Timedelta(days=1))
            times = times.strftime("%Y-%m-%d %H:%M:%S")

            # Write each time-value pair to the CSV
            for t, v in zip(times, values):
                f_out.write(f"{study_ID},{timestep},{units},{t},{value},{kind},{v}\n")
