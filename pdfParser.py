import pandas as pd
import json
import os
import re


def clean_column_names(df):
    """Cleans DataFrame column names."""
    new_columns = {}
    for col in df.columns:
        # Replace newline characters and multiple spaces with a single space
        clean_col = re.sub(r'\s+', ' ', str(col)).strip()
        new_columns[col] = clean_col
    df.rename(columns=new_columns, inplace=True)
    return df


def parse_excel_and_save_json(excel_path, output_dir='output_json'):
    """
    Parses an Excel file, groups by 'SECTIUNEA', sorts by 'cod rand',
    and saves each section to a separate JSON file.
    """
    if not os.path.exists(excel_path):
        print(f"Error: Input file not found at '{excel_path}'")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        # Load the Excel file
        df = pd.read_excel(excel_path, engine='openpyxl')

        # Clean column names
        df = clean_column_names(df)

        # Verify required columns exist
        if 'SECTIUNEA' not in df.columns or 'cod rand' not in df.columns:
            print("Error: 'SECTIUNEA' or 'cod rand' columns not found in the Excel file.")
            return

        # Replace NaN values with None for proper JSON null representation
        df = df.where(pd.notna(df), None)

        # Get unique sections
        sections = df['SECTIUNEA'].unique()

        # Filter out None or empty section names
        sections = [s for s in sections if s]

        for section in sections:
            # Filter dataframe for the current section
            section_df = df[df['SECTIUNEA'] == section].copy()

            # Convert to a list of dictionaries
            # The 'orient='records'' parameter creates a list of dicts
            records = section_df.to_dict(orient='records')

            # Sort the list of dictionaries by 'cod rand'
            # Using a lambda function as the key for robustness
            sorted_records = sorted(records, key=lambda x: x.get('cod rand', 0))

            # Create a filename for the JSON output
            # Sanitize the section name to be a valid filename
            sanitized_section_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(section))
            json_filename = f"{sanitized_section_name}_anexa_2.json"
            json_filepath = os.path.join(output_dir, json_filename)

            # Save the sorted data to a JSON file
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(sorted_records, f, ensure_ascii=False, indent=4)

            print(f"Successfully saved '{json_filepath}'")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == '__main__':
    # Assuming the Excel file is named 'anexa_2.xlsx' and is in the same directory
    # We read all the xlsx files in the given directory and push them to the parsing function
    excel_file_path = 'BugetTm'

    parse_excel_and_save_json()
