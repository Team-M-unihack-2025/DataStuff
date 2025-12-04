import json
import sys
import os
from typing import Dict, List, Set


def find_root_elements(data: Dict) -> List[str]:
    """Find elements that are not subcategories of any other element."""
    # Use set for O(1) lookup instead of list
    all_subcategories: Set[str] = set()
    for value in data.values():
        if isinstance(value, dict) and 'subCategories' in value:
            all_subcategories.update(value['subCategories'])

    root_elements = [key for key in data.keys() if key not in all_subcategories]
    return root_elements


def process_anexa(number: int, input_dir: str = 'structured_output', output_dir: str = 'structured_output') -> bool:
    """Process a single anexa file and add root element."""
    input_file = os.path.join(input_dir, f'SECTIUNEA_TOTAL_anexa_{number}_structured.json')
    output_file = os.path.join(output_dir, f'SECTIUNEA_TOTAL_anexa_{number}_structured_with_roots.json')
    
    if not os.path.exists(input_file):
        print(f"⚠️  Warning: File not found: {input_file}")
        return False
    
    try:
        # Load the JSON file
        with open(input_file, 'r', encoding='utf-8') as f:
            budget_data = json.load(f)

        # Find root elements
        roots = find_root_elements(budget_data)

        # Create a new root element containing all roots as subcategories
        all_roots_element = {
            "00.00": {
                "value": sum(
                    budget_data[root].get('value', 0) 
                    for root in roots 
                    if root in budget_data and isinstance(budget_data[root], dict)
                ),
                "name": "ALL ROOT ELEMENTS",
                "subCategories": sorted(roots)
            }
        }

        # Add to the budget data
        budget_data.update(all_roots_element)

        # Print the new root element
        print(f"\nProcessing anexa {number}:")
        print(json.dumps(all_roots_element, indent=2, ensure_ascii=False))

        # Save updated data
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(budget_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Created root element '00.00' with {len(roots)} subcategories")
        print(f"✓ Saved to {output_file}")
        return True
        
    except Exception as e:
        print(f"✗ Error processing anexa {number}: {e}")
        return False


def main():
    """Process all anexa files or a specific one from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Process budget anexa files and add root elements.'
    )
    parser.add_argument(
        'numbers',
        nargs='*',
        type=int,
        help='Specific anexa numbers to process (default: 2-7)'
    )
    parser.add_argument(
        '--input-dir',
        default='structured_output',
        help='Input directory containing anexa files'
    )
    parser.add_argument(
        '--output-dir',
        default='structured_output',
        help='Output directory for processed files'
    )
    
    args = parser.parse_args()
    
    # Use provided numbers or default to 2-7
    numbers = args.numbers if args.numbers else list(range(2, 8))
    
    success_count = 0
    for number in numbers:
        if process_anexa(number, args.input_dir, args.output_dir):
            success_count += 1
    
    print(f"\n{'='*50}")
    print(f"Processed {success_count}/{len(numbers)} anexa files successfully")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
