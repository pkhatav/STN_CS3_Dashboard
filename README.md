## Setup

### Use the provided environment.yml file
```
conda env create -f environment.yml   
conda activate RasCommander   
cd path\to\your\folder  
python [script_name].py
```

## Run
0. If using WEAP, see the instructions below before running
1.	Add CalSim CSVs or DSS files to the **data folder**
2.	Edit the **input.txt file** in the input_files folder to include this information for each file added in the data folder (adding commas in between):   
* Model Name  
  * Any text excluding commas  
* File Location or WEAP Area   
  * CalSim: Relative path in the data folder (ending in .csv or .dss)   
  * WEAP: Exact area name (case-sensitive)  
* Type
  * Historical, Base, or Scenario
  * One model must have type "Historical" (but no more than one) - if using the historical data, this will be it 
  * One model must have type "Base" (but no more than one)  
* Study  
  * CalSim: Historical or Planning  
  * WEAP: SacWAM or SJWAM  
3.	Run the first script, `00_gethistoricaldata.py`
4.	Run the second script, `01_producemergedcsv.py` (may take a while)
5.	Run the third script, `02_rundashboard.py` (click on the link that says “Dash is running on [link]”)

### WEAP instructions:
1. First, set your WEAP favorites to the eight or so listed in input_files/dashboard_name_mapping.xlsx (WEAP Favorites sheet). Make sure the names match, everything is selected, and that they aren't in a folder. Everything can be exported in TAF.
2. Afterwards, follow the run steps to add the exact WEAP area name(s) to the input.txt file
3. Finally, make sure WEAP is open before running the code

### Example input.txt:
| Model Name | File Location or WEAP Area | Type | Study |
|:-----------|:--------------|:-----|:-----------------------------|
| Mekong 1.3.3 | data/CS3HIST_Mekong_v1.3.3_DV.csv | Base | Historical |
| I6 | data/I6_NewGWDLL_Base_SODTrans.dss | Scenario | Planning |
| SacWAM_2024_Hist | SacWAM_10.02.24 | Historical | SacWAM |
| SJWAM Fix | SJWAM_2026_02_10 | Scenario | SJWAM |

### Optional input file edits:
- Add additional historical data to the CS3HIST DivData MekongV1.2 sheet in historical_data.xlsx, following the same formatting (i.e. matching the "Dashboard Kind" to CalSim data and using -2 for missing values)
- Add additional validation variables to the val_variables.csv file, following the same formatting (brackets, 'quotations,' +/- 1 to sum/subtract, and 'c' coefficients to convert from CFS to TAF)
- Export or map more WEAP variables in the dashboard_name_mapping.xlsx workbook, following the same formatting (more information in the ReadMe sheet)
