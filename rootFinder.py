import json

number = 7
def find_root_elements(data):
    """Find elements that are not subcategories of any other element."""
    all_subcategories = set()
    for key, value in data.items():
        if isinstance(value, dict) and 'subCategories' in value:
            all_subcategories.update(value['subCategories'])

    root_elements = [key for key in data.keys() if key not in all_subcategories]
    return root_elements


# Load the JSON file
with open(f'structured_output/SECTIUNEA_TOTAL_anexa_{number}_structured.json', 'r', encoding='utf-8') as f:
    budget_data = json.load(f)

# Find root elements
roots = find_root_elements(budget_data)

# Create a new root element containing all roots as subcategories
all_roots_element = {
    "00.00": {
        "value": sum(budget_data[root]['value'] for root in roots if 'value' in budget_data[root]),
        "name": "ALL ROOT ELEMENTS",
        "subCategories": sorted(roots)
    }
}

# Add to the budget data
budget_data.update(all_roots_element)

# Print the new root element
print(json.dumps(all_roots_element, indent=2, ensure_ascii=False))

# Save updated data
with open(f'structured_output/SECTIUNEA_TOTAL_anexa_{number}_structured_with_roots.json', 'w', encoding='utf-8') as f:
    json.dump(budget_data, f, indent=2, ensure_ascii=False)

print(f"\n✓ Created root element '00.00' with {len(roots)} subcategories")
print(f"✓ Saved to structured_output/SECTIUNEA_TOTAL_anexa_{number}_structured_with_roots.json")
