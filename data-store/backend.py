from flask import Flask, jsonify, request
from flask_cors import CORS
from typing import Dict, List, Optional
import json
from pathlib import Path

from solana.rpc.api import Client
from solders.pubkey import Pubkey

# Import from your solana modules
from solReader import read_node_from_chain, traverse_hierarchy
from solWriter import load_program_id

app = Flask(__name__)
CORS(app)

# Configuration
RPC_URL = "https://api.devnet.solana.com"
PROGRAM_ID = load_program_id()
client = Client(RPC_URL)

# Load budget mapping
MAPPING_FILE = Path("budget_accounts.json")
PDA_MAP_DIR = Path("..")


def get_node_with_children(category_code: str) -> Optional[Dict]:
    """Helper to get a node with its immediate children in nested format"""
    result = read_node_from_chain(client, category_code, PROGRAM_ID)

    if not result:
        return None

    key, data = result

    # Create nested subcategories dict
    subcategories_dict = {}
    for sub_code in data.get('subCategories', []):
        sub_result = read_node_from_chain(client, sub_code, PROGRAM_ID)
        if sub_result:
            sub_key, sub_data = sub_result
            child_obj = {
                'name': sub_data.get('name'),
                'subCategories': sub_data.get('subCategories', [])
            }
            # Only add value if it exists and is not None/0
            if sub_data.get('value') is not None:
                child_obj['value'] = sub_data.get('value')

            subcategories_dict[sub_key] = child_obj

    response = {
        'name': data.get('name'),
        'subCategories': subcategories_dict
    }

    # Only add value if it exists and is not None/0
    if data.get('value') is not None:
        response['value'] = data.get('value')

    return response


def load_budget_mapping() -> Dict[str, str]:
    """Load mapping of budget files to their PDA maps"""
    if not MAPPING_FILE.exists():
        return {}
    with open(MAPPING_FILE, 'r') as f:
        return json.load(f)


def load_pda_map(pda_map_file: str) -> Dict[str, str]:
    """Load PDA mapping for a specific budget file"""
    pda_path = PDA_MAP_DIR / pda_map_file
    if not pda_path.exists():
        return {}
    with open(pda_path, 'r') as f:
        return json.load(f)


@app.route('/api/budget/<path:budget_id>/root', methods=['GET'])
def get_budget_root(budget_id: str):
    """Get root category (00.00) for a specific budget with immediate children"""
    try:
        result = get_node_with_children("00.00")
        if not result:
            return jsonify({'error': 'Root category not found'}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/budget/<path:budget_id>/category/<category_code>', methods=['GET'])
def get_category(budget_id: str, category_code: str):
    """Get specific category data with immediate children"""
    try:
        result = get_node_with_children(category_code)
        if not result:
            return jsonify({'error': f'Category {category_code} not found'}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/api/budget/<path:budget_id>/hierarchy', methods=['GET'])
def get_hierarchy(budget_id: str):
    """Get full hierarchy starting from a category"""
    try:
        start_key = request.args.get('start', '00.00')
        hierarchy = traverse_hierarchy(client, start_key, PROGRAM_ID)

        # Convert to JSON-serializable format
        result = [
            {'key': key, 'data': data}
            for key, data in hierarchy
        ]

        return jsonify({
            'startKey': start_key,
            'totalNodes': len(result),
            'hierarchy': result
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/budget/<path:budget_id>/search', methods=['GET'])
def search_categories(budget_id: str):
    """Search categories by name or code"""
    try:
        query = request.args.get('q', '').lower()
        if not query:
            return jsonify({'results': []})

        # Get all nodes from hierarchy
        hierarchy = traverse_hierarchy(client, "00.00", PROGRAM_ID)

        # Filter by query
        results = []
        for key, data in hierarchy:
            name = data.get('name', '').lower()
            if query in key.lower() or query in name:
                results.append({
                    'key': key,
                    'name': data.get('name', ''),
                    'value': data.get('value', 0)
                })

        return jsonify({'results': results[:20]})  # Limit to 20 results
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/budget/<path:budget_id>/compare', methods=['POST'])
def compare_categories(budget_id: str):
    """Compare multiple categories"""
    try:
        category_codes = request.json.get('categories', [])
        if not category_codes:
            return jsonify({'error': 'No categories provided'}), 400

        comparison = []
        for code in category_codes:
            result = read_node_from_chain(client, code, PROGRAM_ID)
            if result:
                key, data = result
                comparison.append({
                    'key': key,
                    'name': data.get('name', ''),
                    'value': data.get('value', 0),
                    'subCategories': data.get('subCategories', [])
                })

        return jsonify({'comparison': comparison})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test RPC connection
        version = client.get_version()

        # Test program exists
        program_info = client.get_account_info(PROGRAM_ID)

        return jsonify({
            'status': 'healthy',
            'rpc': RPC_URL,
            'program': str(PROGRAM_ID),
            'programExists': program_info.value is not None,
            'rpcVersion': version.value if hasattr(version, 'value') else str(version)
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get overall statistics"""
    try:
        mapping = load_budget_mapping()

        total_nodes = 0
        total_budgets = len(mapping)

        for pda_map_file in mapping.values():
            pda_map = load_pda_map(pda_map_file)
            total_nodes += len(pda_map)

        return jsonify({
            'totalBudgets': total_budgets,
            'totalNodes': total_nodes,
            'rpc': RPC_URL,
            'program': str(PROGRAM_ID)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print(f"Starting Budget Viewer Backend")
    print(f"RPC: {RPC_URL}")
    print(f"Program: {PROGRAM_ID}")
    print(f"Server running on http://localhost:5000")
    app.run(debug=True, port=5000)
