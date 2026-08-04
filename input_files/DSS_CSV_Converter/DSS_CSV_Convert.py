import os
import shutil
import pandas as pd
from itertools import islice
from multiprocessing import Process
from ras_commander import RasDss

# =====================================================================
# GLOBAL HELPERS — must be TOP LEVEL for Windows multiprocessing
# =====================================================================

def chunked(iterable, size):
    """Yield successive size-length chunks from iterable."""
    it = iter(iterable)
    while True:
        batch = list(islice(it, size))
        if not batch:
            break
        yield batch


def process_batch(dss_file, output_folder, batch_paths, batch_index, total_batches):
    """Worker: bulk-read a batch of DSS paths using RasCommander."""
    print(f"[Process {batch_index}] Starting batch {batch_index}/{total_batches} ({len(batch_paths)} paths)...")

    # ---- BULK READ ----
    results = RasDss.read_multiple_timeseries(dss_file, batch_paths)

    for path, ts_df in results.items():
        try:
            A, B, C, D, E, F = path.strip("/").split("/")
        except:
            print(f"[Process {batch_index}] WARNING: Unparseable path: {path}")
            continue

        variable = B
        kind = C.lower()
        timestep = E
        units = ts_df.attrs.get("units", "")

        # Convert to datetime
        times = pd.to_datetime(ts_df.index)
        values = ts_df.iloc[:, 0].values

        # === APPLY ORIGINAL DATE FIXES ===
        times = times - pd.Timedelta(days=1)

        # === NEW CUTOFF ===
        # Adjusted minimum timestamp allowed in output
        # (after date correction): 1921‑10‑31 00:00:00
        cutoff = pd.Timestamp("1921-10-31 00:00:00")
        mask = times >= cutoff
        times = times[mask]
        values = values[mask]

        if len(times) == 0:
            print(f"[Process {batch_index}] Path {path} has no data after cutoff → skipped.")
            continue

        times_str = times.strftime("%Y-%m-%d %H:%M:%S")

        # === Construct per-path CSV ===
        df = pd.DataFrame({
            "id": 0,
            "Timestep": timestep,
            "Units": units,
            "Date_Time": times_str,
            "Variable": variable,
            "Kind": kind,
            "Value": values
        })

        safe = path.replace("/", "_").strip("_") + ".csv"
        outfile = os.path.join(output_folder, safe)
        df.to_csv(outfile, index=False)

    print(f"[Process {batch_index}] Finished batch {batch_index}/{total_batches}")


# =====================================================================
# MAIN DSS→CSV CONVERTER (RasCommander version)
# =====================================================================

def convert_to_csv(
        dss_file,
        fv_file,
        output_folder="output_timeseries",
        batch_size=500,
        parallel_jobs=8):

    """Convert DSS→CSV using RasCommander, matching the original DSSVue CSV format."""

    if os.path.isdir(output_folder):
        shutil.rmtree(output_folder) # delete old output timeseries first
    
    os.makedirs(output_folder)

    print("=== RASCommander Parallel DSS Extractor ===")

    # ------------------------------------------------------------
    # 1. FV file — Uses ONLY Part B (same as your original script)
    # ------------------------------------------------------------
    fv_df = pd.read_csv(fv_file)
    fv_df["Part B"] = fv_df["Part B"].astype(str).str.strip()

    # ------------------------------------------------------------
    # 2. Load DSS catalog & split into A/B/C/D/E/F
    # ------------------------------------------------------------
    catalog = RasDss.get_catalog(dss_file)
    catalog["pathname"] = catalog["pathname"].str.strip()

    parts = catalog["pathname"].str.strip("/").str.split("/", expand=True)
    parts = parts.reindex(columns=range(6), fill_value="")
    parts.columns = ["A", "B", "C", "D", "E", "F"]
    catalog = pd.concat([catalog, parts], axis=1)

    for col in ["A", "B", "C", "D", "E", "F"]:
        catalog[col] = catalog[col].astype(str).str.strip()

    # ------------------------------------------------------------
    # 3. Filter only Part D == 01JAN1920 (planning), D == 01JAN2000 (hist)
    # ------------------------------------------------------------
    
    if fv_file == "input_files/fv/planning_model_variables.fv":
        catalog = catalog[catalog["D"].str.upper() == "01JAN1920"]
        print(f"Catalog after D-part filter: {len(catalog)} rows")
    #elif fv_file == "input_files/fv/hist_model_variables.fv":
        #catalog = catalog[catalog["D"].str.upper() == "01JAN2000"]
        #print(f"Catalog after D-part filter: {len(catalog)} rows")

    # ------------------------------------------------------------
    # 4. Match only by Part B (your original workflow)
    # ------------------------------------------------------------
    matched_paths = []

    for _, row in fv_df.iterrows():
        partB = row["Part B"]
        hits = catalog[catalog["B"] == partB]
        matched_paths.extend(list(hits["pathname"]))

    matched_paths = list(dict.fromkeys(matched_paths))  # dedupe
    print(f"Matched unique DSS paths: {len(matched_paths)}")

    # ------------------------------------------------------------
    # 5. PARALLEL BATCH EXTRACTION
    # ------------------------------------------------------------
    batches = list(chunked(matched_paths, batch_size))
    total_batches = len(batches)

    print(f"Processing {total_batches} batches using {parallel_jobs} processes...\n")

    processes = []

    for i, batch in enumerate(batches, start=1):
        p = Process(
            target=process_batch,
            args=(dss_file, output_folder, batch, i, total_batches)
        )
        processes.append(p)
        p.start()

        # enforce maximum concurrent workers
        if len(processes) >= parallel_jobs:
            for p in processes:
                p.join()
            processes = []

    for p in processes:
        p.join()

    print("All batches complete.\n")

    # ------------------------------------------------------------
    # 6. Memory-safe long-format COMBINATION
    # ------------------------------------------------------------
    print("Combining all per-path CSVs into final long-format file...")

    # === Final CSV is placed next to DSS file with same name ===
    dss_basename = os.path.splitext(os.path.basename(dss_file))[0]
    dss_folder = os.path.dirname(dss_file)
    master_csv = os.path.join(dss_folder, dss_basename + ".csv")

    expected_cols = ["id", "Timestep", "Units", "Date_Time", "Variable", "Kind", "Value"]

    # Write header
    with open(master_csv, "w") as f_out:
        f_out.write(",".join(expected_cols) + "\n")

    csv_files = [
        os.path.join(output_folder, f)
        for f in os.listdir(output_folder)
        if f.lower().endswith(".csv")
    ]

    total_rows = 0

    for f in csv_files:
        try:
            df = pd.read_csv(f, dtype=str)

            # Ensure consistent schema
            if not set(expected_cols).issubset(df.columns):
                print(f"Skipping malformed CSV: {f}")
                continue

            df = df[expected_cols]

            if df.empty:
                continue

            df.to_csv(master_csv, mode="a", header=False, index=False)
            total_rows += len(df)

        except Exception as e:
            print(f"Skipping unreadable CSV: {f}")
            print(e)
            continue

    print(f"Combined {total_rows} rows into {master_csv}")
    print("=== DONE ===")
