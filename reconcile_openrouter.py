import argparse
import json
import os
import sys
import glob
from openai import OpenAI


def get_openrouter_client():
    """Initializes and returns the OpenAI client configured for OpenRouter."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def load_json_file(file_path):
    """Loads content from a single JSON file path."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found at '{file_path}'", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{file_path}'", file=sys.stderr)
        return None


def reconcile_and_save_data(client, data, model_name, output_path):
    """Sends data to an OpenRouter model for restructuring and saves the JSON output."""
    data_string = json.dumps(data, indent=2, ensure_ascii=False)
    # Updated prompt with more detailed instructions for the model
    prompt = f"""
    You are an expert data processor specializing in JSON transformations and an expert accountant specialised in Romanian Public Administration Budgets and Laws. 
    Your task is to analyze the provided flat JSON object and add a hierarchical structure by identifying parent-child relationships within the keys.
    
    **Examples:**
    -  00.02 is a direct child of 00.01 because 00.01 is TOTAL VENITURI and 00.02 is a subcategory of it VENITURI PROPRII.
    -  00.05 is a direct child of 00.04 because 00.04 is A. VENITURI FISCALE and 00.05 is A1. IMPOZIT PE VENIT, PROFIT SI CASTIGURI DIN CAPITAL
    -  03.00.01 is a child of 00.05 because 00.05 is A1. IMPOZIT PE VENIT, PROFIT SI CASTIGURI DIN CAPITAL and 03.00.01 is A12. IMPOZIT PE VENIT, PROFIT, SI CASTIGURI DIN CAPITAL DE LA PERSOANE FIZICE
    -  12.02A.07 is the child of 12.02A because 12.02A is ALTE IMPOZITE SI TAXE GENERALE PE BUNURI SI SERVICII and 12.02A.07 is Taxe hoteliere
    - `07.02A.01` IS a direct child of `07.02A`.
    - `07.02A.01.01` IS NOT a direct child of `07.02A` (it's a grandchild).
    - `07.02A.01.01` IS a direct child of `07.02A.01`.
    
    **Format Example:**
    {{
  "00.01": {{
    "value": 2388257760.0,
    "name": "TOTAL VENITURI",
    "subCategories": [
      "00.02",
      "39.00.01",
      "42.00.01"
    ]
  }},
  "00.02": {{
    "value": 1278943070.0,
    "name": "VENITURI PROPRII",
    "subCategories": [
      "00.03",
      "39.00.01",
      "42.00.01"
    ]
  }},
  "00.03": {{
    "value": 1552087790.0,
    "name": "I. VENITURI CURENTE",
    "subCategories": [
      "00.04",
      "30.00.01"
    ]
  }},
  "00.04": {{
    "value": 1494469860.0,
    "name": "A. VENITURI FISCALE",
    "subCategories": [
      "00.05",
      "07.00.01",
      "11.00.01",
      "12.02A",
      "18.00.01"
    ]
  }},
  "00.05": {{
    "value": 890293620.0,
    "name": "A1. IMPOZIT PE VENIT, PROFIT SI CASTIGURI DIN CAPITAL"
  }},
  }}

    **Input Data to Process:**
    {data_string}

    Return only the complete, restructured JSON object.
    """

    try:
        print(f"\n--- Sending request for '{os.path.basename(output_path)}' to model '{model_name}'... ---")
        response = client.chat.completions.create(
            model=model_name,
            messages=[{'role': 'user', 'content': prompt}],
            response_format={"type": "json_object"}
        )

        response_content = response.choices[0].message.content
        print(f"\n--- Received response: {response_content}\n")
        parsed_json = json.loads(response_content)

        # Save the structured JSON to the output file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(parsed_json, f, indent=2, ensure_ascii=False)

        print(f"--- Successfully saved structured file to '{output_path}' ---")

    except json.JSONDecodeError:
        print(f"\nError: Failed to decode JSON response for '{output_path}'.", file=sys.stderr)
        # print("Received content:", response_content, file=sys.stderr) # Uncomment for debugging
    except Exception as e:
        print(f"\nAn error occurred while processing for '{output_path}': {e}", file=sys.stderr)


def main():
    """Main function to find, process, and save structured JSON files."""
    parser = argparse.ArgumentParser(
        description="Restructure budget JSON files from a directory using an OpenRouter model."
    )
    parser.add_argument('input_dir', help="Path to the directory containing input JSON files.")
    parser.add_argument('output_dir', help="Path to the directory to save output files.")
    parser.add_argument(
        '--model',
        default='minimax/minimax-m2',
        help="The name of the OpenRouter model to use."
    )
    args = parser.parse_args()

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    # Find all JSON files in the input directory
    search_path = os.path.join(args.input_dir, '*.json')
    all_json_files = glob.glob(search_path)

    # Filter for files containing the specified keyword
    files_to_process = [
        f for f in all_json_files
        if 'SECTIUNEA_TOTAL' in f
    ]

    if not files_to_process:
        print(f"No files containing 'SECTIUNEA_TOTAL' found in '{args.input_dir}'.")
        return

    client = get_openrouter_client()

    for input_path in files_to_process:
        print(f"Processing file: '{input_path}'")
        data = load_json_file(input_path)
        if data:
            base_filename = os.path.basename(input_path)
            output_filename = f"{os.path.splitext(base_filename)[0]}_structured.json"
            output_path = os.path.join(args.output_dir, output_filename)

            reconcile_and_save_data(client, data, args.model, output_path)


if __name__ == "__main__":
    main()