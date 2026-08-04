## Setup

### Option 1: Download Python (this code needs to be run in version 3.13)
Open Command Prompt and write the following lines (one by one):   
```
cd path\to\your\folder   
pip install ras_commander openpyxl pyjnius xlsxwriter dash==3.4.0   
python [script_name].py  
```

### Option 2: Alternatively, create an environment in Anaconda prompt (assuming you have Anaconda installed):
```
conda create -n [env_name] python=3.13   
conda activate [env_name]  
pip install ras_commander openpyxl pyjnius xlsxwriter dash==3.4.0   
cd path\to\your\folder  
python [script_name].py
```

When running the dashboard - click on the link that says “Dash is running on [link]”   

## Run
1.	Add CalSim CSVs or DSS files to the data folder
2.	Edit the input.txt file in the input_files folder to add a model name, path location (ending in either .dss or .csv), the type of model (Historical, Base, or Scenario), and whether it is a historical or planning study model (Historical or Planning) for each file added in the data folder
3.	Optional: Edit the historical_data.xlsx workbook, following the same formatting
4.	Run the first script, `00_gethistoricaldata.py`
5.	Optional: Edit the val_variables.csv file, following the same formatting
6.	Run the second script, `01_producemergedcsv.py` (may take a while)
7.	Run the third script, `02_rundashboard.py`
