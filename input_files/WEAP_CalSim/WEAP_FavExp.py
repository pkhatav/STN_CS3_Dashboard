import win32com.client
import os
import csv
import shutil

def export_weap_favorites(weap_area):
    '''
    This function will export whatever WEAP model you have open as CSV files for each favorite you have set. 
    They will be saved in the data folder under "WEAP_Favorites_Exports"
    '''
    
    # Notes
    print("---------------------------------------------------------------")
    print("PLEASE KEEP WEAP OPEN AND RESPOND TO ANY PROMPTS ON THE SCREEN!")
    print("---------------------------------------------------------------")
    
    # Connect to WEAP
    WEAP = win32com.client.Dispatch("WEAP.WEAPApplication")
    
    # Set WEAP visible (optional)
    WEAP.Visible = 1  

    # Open a model (area)
    try:
        WEAP.ActiveArea = weap_area
        print(f"Opened: {WEAP.ActiveArea.Name}")
    
    except Exception as e:
        raise ValueError(f"WEAP area '{weap_area}' does not exist") from e
    
    # Folder where this .py file lives
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create export folder in the data folder
    export_dir = os.path.join(
        script_dir,
        "..",
        "..",
        "data",
        "WEAP_Favorites_Exports"
    )
    export_dir = os.path.abspath(export_dir)
    
    # Delete old exports if they exist
    if os.path.isdir(export_dir):
        shutil.rmtree(export_dir)

    # Ensure export directory exists
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    print("Export folder:", export_dir)
    
    # Loop through all favorites
    for fav in WEAP.Favorites:
        fav_name = str(fav.Name)  # Get the favorite's name as a string
        safe_name = fav_name.replace(" ", "_").replace("/", "_")  # Clean filename
    
        export_path = os.path.join(export_dir, f"{safe_name}.csv")
        
        print(f"Exporting: {fav_name} -> {export_path}")
        
        # Load the favorite (activate it)
        WEAP.LoadFavorite(fav_name)  
        
        # Export results
        WEAP.ExportResults(export_path, True, True, False, False, False, False, False, False, False, True)  # True = Include headers
    
        print(f"Successfully exported: {os.path.exists(export_path)}")
    
    print("All favorites exported!")