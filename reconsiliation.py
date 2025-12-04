import json
import os


def get_total_from_json(file_path: str) -> float:
    """
    Reads a JSON file and calculates the sum of all 'value' fields
    at the top level of the JSON object.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        float: The sum of all values, or 0.0 if the file is not found or empty.
    """
    if not os.path.exists(file_path):
        print(f"⚠️  Warning: File not found at '{file_path}'. Returning 0.")
        return 0.0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Sum the 'value' from each top-level entry in the JSON object more efficiently
        # Use generator expression to avoid creating intermediate list
        total_sum = sum(
            item.get('value', 0) 
            for item in data.values() 
            if isinstance(item, dict) and 'value' in item
        )
        return total_sum
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{file_path}'.")
        return 0.0
    except Exception as e:
        print(f"An unexpected error occurred while reading {file_path}: {e}")
        return 0.0


def check_anexa_sums(anexa_number: int, base_path: str):
    """
    Checks if the sum of 'DEZVOLTARE' and 'FUNCTIONARE' matches 'TOTAL'
    for a given anexa number using JSON files.

    Args:
        anexa_number (int): The number of the 'anexa' to check.
        base_path (str): The directory containing the JSON files.
    """
    print(f"--- Processing Anexa {anexa_number} ---")

    # Define file paths for the three sections
    path_dezvoltare = os.path.join(base_path, f"SECTIUNEA_DEZVOLTARE_anexa_{anexa_number}.json")
    path_functionare = os.path.join(base_path, f"SECTIUNEA_FUNCTIONARE_anexa_{anexa_number}.json")
    path_total = os.path.join(base_path, f"SECTIUNEA_TOTAL_anexa_{anexa_number}.json")

    # Get the total sum from each file
    sum_dezvoltare = get_total_from_json(path_dezvoltare)
    sum_functionare = get_total_from_json(path_functionare)
    sum_total = get_total_from_json(path_total)

    calculated_total = sum_dezvoltare + sum_functionare

    # Print the results
    print(f"Sum from 'SECTIUNEA_DEZVOLTARE': {sum_dezvoltare:,.2f}")
    print(f"Sum from 'SECTIUNEA_FUNCTIONARE': {sum_functionare:,.2f}")
    print(f"Calculated Total (Dezvoltare + Functionare): {calculated_total:,.2f}")
    print(f"Sum from 'SECTIUNEA_TOTAL' file: {sum_total:,.2f}")

    # Compare the sums and print the validation result
    if abs(calculated_total - sum_total) < 0.01:  # Using a small tolerance for float comparison
        print("\n✅ SUCCESS: The sums match.")
    else:
        difference = calculated_total - sum_total
        print(f"\n❌ FAILURE: The sums do not match. Difference: {difference:,.2f}")

    print("-" * 30 + "\n")


if __name__ == '__main__':
    # --- IMPORTANT ---
    # This script will look for JSON files in the 'output_json' directory.
    # Change 'json_directory' if your files are in a different location.
    json_directory = 'output_json'

    for number in range(2, 8):  # This will loop from 2 to 7
        check_anexa_sums(number, json_directory)
