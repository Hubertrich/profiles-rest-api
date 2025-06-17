import glob
import pandas as pd
import psycopg2  # PostgreSQL adapter
from tqdm import tqdm
import numpy as np
import warnings
import datetime 
import xlsxwriter
from sqlalchemy import create_engine
from sqlalchemy import text  # Import text() for raw SQL

warnings.filterwarnings('ignore')
start = datetime.datetime.now()
print(f"start: {start}")

# PostgreSQL local database settings
username = "postgres"  # Default PostgreSQL user
password = "23423456Hu"  # Use the password you set during installation
host = "localhost"  # Running locally
port = "5432"  # Default PostgreSQL port

# Connection for reading data (valiant_data)
read_db = "valiant_data"
# Connection for writing data (my_local_database)
write_db = "my_local_database"

# Find all Excel files
list_files = glob.glob('data-beban-penyulang/*.xlsx')

#start and end years for analysis
start_year = 2018
end_year = 2023

# Start with part 1: modular DB connection

def create_engine_connections(username, password, host, port, read_db, write_db):
    from sqlalchemy import create_engine
    
    read_engine = create_engine(f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{read_db}")
    write_engine = create_engine(f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{write_db}")

    return read_engine, write_engine


def test_db_connections(read_engine, write_engine, read_db, write_db, host, port):
    try:
        with read_engine.connect() as conn:
            print(f"Successfully connected to {read_db} at {host}:{port}")
    except Exception as e:
        print(f"Database connection to {read_db} failed:", e)

    try:
        with write_engine.connect() as conn:
            print(f"Successfully connected to {write_db} at {host}:{port}")
    except Exception as e:
        print(f"Database connection to {write_db} failed:", e)


# Part 2: raw Excel data loader

def load_excel_to_postgres(list_files, read_engine, table_name="beban_penyulang"):
    with read_engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {table_name}"))
        conn.commit()

    for file in tqdm(list_files, desc="Processing Excel files"):
        with pd.ExcelFile(file) as xls:
            for sh in xls.sheet_names:
                temp = pd.read_excel(xls, sheet_name=sh)
                cols = [col for col in temp.columns if isinstance(col, str) and any(name in col.lower() for name in ['time', 'gi'])]
                if not cols:
                    continue

                temp = temp[cols]
                df_long = temp.melt(id_vars=["Time"], var_name="substation", value_name="value")
                df_long.rename(columns={"Time": "time"}, inplace=True)
                df_long["time"] = pd.to_datetime(df_long["time"], errors="coerce", utc=True)

                df_long.to_sql(table_name, read_engine, if_exists="append", index=False)

    print("All raw file data successfully inserted into PostgreSQL!")

# Part 3: pivot and reshape back into wide format

def get_pivoted_data(read_engine, table_name="beban_penyulang"):
    data = pd.read_sql(f"SELECT * FROM {table_name}", read_engine)
    data = data.pivot(index="time", columns="substation", values="value").reset_index()
    data.rename(columns={"time": "Time"}, inplace=True)
    data.columns.name = None
    return data


# Part 4: analyze energy and peak load and outage duration

def analyze_peak_energy_downtime(data, keyword="gi", start_year=None, end_year=None):
    """
    Analyzes energy, peak load, and outage duration per feeder (GI-based) per month and year.
    
    Returns two DataFrames:
    - df: summary with Year, Bulan, Penyulang, Peak Load, Energy, Dur
    - db_penyulang: same as df with alternate naming (peak_load, energy, dur)
    """
    time_delta = 1 / (data['Time'].diff().dt.total_seconds().dropna()[1] / 3600)
    data['Time'] = pd.to_datetime(data['Time'])

    df = pd.DataFrame()
    db_penyulang = pd.DataFrame()

    for yr in tqdm(range(start_year, end_year + 1), desc="Tahun"):
        for mt in range(1, 13):
            temp = data[(data['Time'].dt.month == mt) & (data['Time'].dt.year == yr)]

            # Find relevant feeder columns
            cols = []
            for col_name in data.columns:
                col = col_name.lower().split(',')
                if len(col) == 1:
                    if keyword.lower() in col[0]:
                        cols.append(col_name)
                else:
                    if keyword.lower() in col[0] and 'inc' not in col[1]:
                        cols.append(col_name)
            cols = list(set(cols))
            temp = temp[cols]
            temp.dropna(axis=1, how='all', inplace=True)

            for col in temp.columns:
                temp[col] = temp[col].fillna(0)
                if temp[col].dtype == 'object':
                    temp[col][temp[col].str.contains('-|#', na=False)] = 0

                temp[col] = temp[col].astype(float)
                off_dur = np.sum(temp[col] == 0)
                i = df.shape[0]

                df.loc[i, 'Year'] = yr
                db_penyulang.loc[i, 'year'] = yr

                df.loc[i, 'Bulan'] = mt
                db_penyulang.loc[i, 'bulan'] = mt

                df.loc[i, 'penyulang'] = col
                db_penyulang.loc[i, 'penyulang'] = col

                df.loc[i, 'Peak Load'] = np.max(temp[col]) * 20 * np.sqrt(3.0)
                db_penyulang.loc[i, 'peak_load'] = np.max(temp[col]) * 20 * np.sqrt(3.0)

                df.loc[i, 'Energy'] = np.sum(temp[col]) / time_delta * 20 * np.sqrt(3.0)
                db_penyulang.loc[i, 'energy'] = np.sum(temp[col]) / time_delta * 20 * np.sqrt(3.0)

                df.loc[i, 'Dur'] = off_dur / time_delta
                db_penyulang.loc[i, 'dur'] = off_dur / time_delta

    return df, db_penyulang


# part  5: summarize energy and peak load 
def summarize_energy_peak(df):
    """
    Converts long-format df with ['Year', 'Bulan', 'penyulang', 'Energy', 'Peak Load'] 
    into wide-format DataFrames for energy and peak load.

    Parameters:
    - df (DataFrame): Output from analyze_peak_energy_downtime function.

    Returns:
    - df_energi (DataFrame): Wide format with Time and feeders as columns (energy values).
    - db_energi (DataFrame): Same as above, different naming (for DB export).
    - df_peak (DataFrame): Wide format with Time and feeders as columns (peak load).
    - db_peak_load (DataFrame): Same as above, different naming (for DB export).
    """
    df_energi = pd.DataFrame()
    db_energi = pd.DataFrame()
    df_peak = pd.DataFrame()
    db_peak_load = pd.DataFrame()

    for year, bulan in df[['Year', 'Bulan']].drop_duplicates().values:
        temp = df[(df['Bulan'] == bulan) & (df['Year'] == year)]
        k = df_energi.shape[0]
        time_str = f'{int(year)}-{int(bulan):02d}'

        # Add year-month to time columns
        df_energi.loc[k, 'Time'] = time_str
        db_energi.loc[k, 'Time'] = time_str
        df_peak.loc[k, 'Time'] = time_str
        db_peak_load.loc[k, 'time'] = time_str

        for penyulang in temp['penyulang'].unique():
            energy = temp[temp['penyulang'] == penyulang]['Energy'].values[0]
            peak = temp[temp['penyulang'] == penyulang]['Peak Load'].values[0]

            df_energi.loc[k, penyulang] = energy
            db_energi.loc[k, penyulang] = energy
            df_peak.loc[k, penyulang] = peak
            db_peak_load.loc[k, penyulang] = peak

    df_energi.fillna(0, inplace=True)
    df_peak.fillna(0, inplace=True)

    return df_energi, db_energi, df_peak, db_peak_load

#  Part 6: Export results to Excel
def export_results(
    df,
    df_energi,
    df_peak,
    db_penyulang,
    db_energi,
    db_peak_load,
    write_engine,
    excel_path="output/res_dist.xlsx"
):
    """
    Exports results to Excel and saves processed tables into PostgreSQL.

    Parameters:
    - df, df_energi, df_peak: DataFrames for Excel (visual purposes only).
    - db_penyulang, db_energi, db_peak_load: Cleaned DataFrames for database export.
    - write_engine: SQLAlchemy engine for writing to PostgreSQL.
    - excel_path (str): Output path for Excel file.
    """
    import os
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)

    # Export to Excel
    with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Penyulang', index=False)
        df_energi.to_excel(writer, sheet_name='Energy', index=False, startrow=3)
        df_peak.to_excel(writer, sheet_name='Peak Load', index=False, startrow=3)
    print(f"Excel file exported to: {excel_path}")

    # Save to PostgreSQL
    db_penyulang.to_sql('d_penyulang', write_engine, if_exists='replace', index=False)
    db_energi.to_sql('d_energi', write_engine, if_exists='replace', index=False)
    db_peak_load.to_sql('d_peak_load', write_engine, if_exists='replace', index=False)
    print("Data saved to PostgreSQL database.")

def run_preprocessing_pipeline(
    excel_folder_path,
    username="postgres",
    password="23423456Hu",
    host="localhost",
    port="5432",
    read_db="valiant_data",
    write_db="my_local_database",
    table_name="beban_penyulang",
    start_year=2018,
    end_year=2023,
    output_excel_path="output/res_dist.xlsx"
):
    start = datetime.datetime.now()

    # Step 1: Create DB connections
    read_engine, write_engine = create_engine_connections(
        username, password, host, port, read_db, write_db
    )
    test_db_connections(read_engine, write_engine, read_db, write_db, host, port)

    # Step 2: Load raw Excel files to raw-data DB
    list_files = glob.glob(f"{excel_folder_path}/*.xlsx")
    load_excel_to_postgres(list_files, read_engine, table_name=table_name)

    # Step 3: Pivot to wide format
    data = get_pivoted_data(read_engine, table_name=table_name)

    # Step 4: Analyze peak, energy, downtime
    df, db_penyulang = analyze_peak_energy_downtime(
        data, keyword="gi", start_year=start_year, end_year=end_year
    )

    # Step 5: Summarize energy and peak
    df_energi, db_energi, df_peak, db_peak_load = summarize_energy_peak(df)

    # Step 6: Export to Excel and DB
    export_results(
        df,
        df_energi,
        df_peak,
        db_penyulang,
        db_energi,
        db_peak_load,
        write_engine,
        excel_path=output_excel_path
    )

    end = datetime.datetime.now()
    print(f"Duration: {end - start}")
    print("All tasks completed successfully!")
    
if __name__ == "__main__":
    # Step 1: Create DB connections
    read_engine, write_engine = create_engine_connections(username, password, host, port, read_db, write_db)
    test_db_connections(read_engine, write_engine, read_db, write_db, host, port)

    # Step 2: Load raw Excel files to raw-data DB (valiant_data)
    load_excel_to_postgres(list_files, read_engine, table_name="beban_penyulang")

    # Step 3: Pivot to wide format
    data = get_pivoted_data(read_engine, table_name="beban_penyulang")

    # Step 4: Analyze peak, energy, downtime
    df, db_penyulang = analyze_peak_energy_downtime(data, keyword="gi", start_year=start_year, end_year=end_year)

    # Step 5: Summarize energy and peak
    df_energi, db_energi, df_peak, db_peak_load = summarize_energy_peak(df)

    # Step 6: Export to Excel and DB
    export_results(
        df,
        df_energi,
        df_peak,
        db_penyulang,
        db_energi,
        db_peak_load,
        write_engine,
        excel_path="output/res_dist.xlsx"
    )

    end = datetime.datetime.now()
    print(f"Durasi: {end - start}")
    print("All tasks completed successfully!")

