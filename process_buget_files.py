"""
Process Excel budget files from BugetTm folder.
Separates data by SECTIUNEA and saves to JSON files ordered by 'cod rand'.
"""

import pandas as pd
import json
import os
import re
from pathlib import Path


def clean_column_names(df):
    """Cleans DataFrame column names by removing extra whitespace."""
    new_columns = {}
    for col in df.columns:
        clean_col = re.sub(r'\s+', ' ', str(col)).strip()
        new_columns[col] = clean_col
    df.rename(columns=new_columns, inplace=True)
    return df


def extract_anexa_number(filename):
    """Extracts anexa number from filename (e.g., 'ANEXA NR. 2' -> '2')."""
    match = re.search(r'ANEXA\s+NR\.?\s*(\d+)', filename, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_sectiunea(text):
    """
    Extracts SECTIUNEA name from the indicator text.
    Looks for patterns like 'SECTIUNEA_TOTAL', 'SECTIUNEA DEZVOLTARE', etc.
    """
    text = str(text).upper()

    # Check for various SECTIUNEA patterns
    if 'SECTIUNEA' in text or 'SECŢIUNEA' in text:
        # Try to extract the full section name
        patterns = [
            r'SECTI[UO]NEA[\s_]*TOTAL[AĂ]?',
            r'SECTI[UO]NEA[\s_]*DEZVOLTARE',
            r'SECTI[UO]NEA[\s_]*FUNC[TŢ]IONARE',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                section = match.group(0)
                # Normalize the name
                section = section.replace('SECŢIUNEA', 'SECTIUNEA')
                section = section.replace(' ', '_')
                section = section.replace('TOTALA', 'TOTAL')
                section = section.replace('FUNCŢIONARE', 'FUNCTIONARE')
                return section

    return None


def process_excel_file(excel_path, output_dir='output_json'):
    """
    Processes a single Excel file, separates by SECTIUNEA,
    and saves each section to a JSON file ordered by 'Cod rand'.

    Args:
        excel_path: Path to the Excel file
        output_dir: Directory to save JSON output files
    """
    print(f"\n{'='*60}")
    print(f"Processing: {os.path.basename(excel_path)}")
    print(f"{'='*60}")

    # Extract anexa number from filename
    anexa_number = extract_anexa_number(os.path.basename(excel_path))
    if not anexa_number:
        print(f"Warning: Could not extract anexa number from {excel_path}")
        return

    try:
        # Read Excel file
        df = pd.read_excel(excel_path, engine='openpyxl')

        # Clean column names
        df = clean_column_names(df)

        # Display columns for debugging
        print(f"Columns found: {df.columns.tolist()}")

        # Check for required columns - using correct column names
        required_cols = ['Cod rand', 'Indicator bugetar', 'Denumirea indicatorului bugetar']
        missing_cols = [col for col in required_cols if col not in df.columns]

        # Find the Total column (it might have variations in spacing)
        total_col = None
        for col in df.columns:
            if 'Total' in col and ('T1' in col or 'T2' in col):
                total_col = col
                break

        if not total_col:
            # Try to find any column starting with "Total"
            for col in df.columns:
                if col.startswith('Total'):
                    total_col = col
                    break

        if missing_cols:
            print(f"Error: Missing required columns: {missing_cols}")
            return

        if not total_col:
            print(f"Error: Could not find Total column")
            print(f"Available columns: {df.columns.tolist()}")
            return

        print(f"Using Total column: '{total_col}'")

        # Replace NaN with None
        df = df.where(pd.notna(df), None)

        # Extract SECTIUNEA from 'Denumirea indicatorului bugetar'
        # SECTIUNEA appears to be in the indicator name (e.g., "SECTIUNEA_TOTAL", "SECTIUNEA_DEZVOLTARE", etc.)
        df['SECTIUNEA_EXTRACTED'] = df['Denumirea indicatorului bugetar'].apply(
            lambda x: extract_sectiunea(str(x)) if pd.notna(x) else None
        )

        # Group rows by their section
        # We need to track which section each row belongs to
        current_section = None
        sections_list = []

        for idx, row in df.iterrows():
            sectiunea_value = row['SECTIUNEA_EXTRACTED']
            if sectiunea_value:
                current_section = sectiunea_value
            sections_list.append(current_section)

        df['SECTIUNEA'] = sections_list

        # Get unique sections, filtering out None/empty values
        sections = df['SECTIUNEA'].unique()
        sections = [s for s in sections if s and str(s).strip()]

        print(f"Found sections: {sections}")

        for section in sections:
            # Filter data for current section
            section_df = df[df['SECTIUNEA'] == section].copy()

            # Remove rows that are section headers themselves
            section_df = section_df[section_df['SECTIUNEA_EXTRACTED'].isna()]

            # Sort by 'Cod rand'
            section_df = section_df.sort_values('Cod rand')

            # Create dictionary with format: "indicator_bugetar": {"value": total, "name": "indicator_name"}
            result = {}
            for _, row in section_df.iterrows():
                indicator_bugetar = str(row['Indicator bugetar']).strip() if pd.notna(row['Indicator bugetar']) else None
                cod_rand = str(row['Cod rand']).strip() if pd.notna(row['Cod rand']) else None
                total_value = row[total_col]
                name = row['Denumirea indicatorului bugetar']

                if indicator_bugetar and indicator_bugetar != 'nan':
                    result[indicator_bugetar] = {
                        "value": float(total_value) if pd.notna(total_value) else 0.0,
                        "name": str(name).strip() if pd.notna(name) else ""
                    }

            # Create filename
            sanitized_section = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(section))
            json_filename = f"{sanitized_section}_anexa_{anexa_number}.json"
            json_filepath = os.path.join(output_dir, json_filename)

            # Save to JSON
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=4)

            print(f"✓ Saved: {json_filename} ({len(result)} entries)")

    except Exception as e:
        print(f"Error processing {excel_path}: {e}")
        import traceback
        traceback.print_exc()


def process_all_buget_files(buget_dir='BugetTm', output_dir='output_json'):
    """
    Processes all Excel files in the BugetTm directory.

    Args:
        buget_dir: Directory containing Excel files
        output_dir: Directory to save JSON output files
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Get all Excel files from BugetTm directory
    buget_path = Path(buget_dir)
    excel_files = list(buget_path.glob('*.xlsx')) + list(buget_path.glob('*.xls'))

    # Filter out temporary files (starting with ~$)
    excel_files = [f for f in excel_files if not f.name.startswith('~$')]

    if not excel_files:
        print(f"No Excel files found in {buget_dir}")
        return

    print(f"\nFound {len(excel_files)} Excel file(s) to process:")
    for f in excel_files:
        print(f"  - {f.name}")

    # Process each file
    for excel_file in excel_files:
        process_excel_file(str(excel_file), output_dir)

    print(f"\n{'='*60}")
    print(f"Processing complete! JSON files saved to '{output_dir}'")
    print(f"{'='*60}")


if __name__ == '__main__':
    # Process all files in BugetTm directory
    process_all_buget_files()
