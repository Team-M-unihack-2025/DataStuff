# solManager.py
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey

# Import from solWriter
from solWriter import (
    HierarchicalDataStore,
    store_all_nodes,
    load_keypair,
    load_program_id,
    ensure_program_exists,
    ensure_rpc_available,
    RPC_URL,
    PROGRAM_ID
)

# Import from solReader
from solReader import (
    read_node_from_chain,
    read_all_nodes,
    traverse_hierarchy,
    print_node_tree
)


class BudgetSolanaManager:
    """Manage budget data on Solana devnet"""

    def __init__(self, rpc_url: Optional[str] = None, program_id: Optional[Pubkey] = None):
        self.rpc_url = rpc_url or RPC_URL
        self.program_id = program_id or PROGRAM_ID
        self.client = Client(self.rpc_url)
        self.payer = load_keypair()
        self.mapping_file = Path("budget_accounts.json")
        self.structured_dir = Path("../structured_output")

    def upload_all(self) -> Dict[str, str]:
        """Upload all budget files to Solana"""
        budget_files = [
            "SECTIUNEA_TOTAL_anexa_2_structured_with_roots.json"
            ]

        uploaded = {}

        print(f"=== Uploading budgets to Solana devnet ===\n")
        print(f"RPC: {self.rpc_url}")
        print(f"Program: {self.program_id}")
        print(f"Payer: {self.payer.pubkey()}\n")

        # Verify RPC and program
        try:
            ensure_rpc_available(self.rpc_url)
            ensure_program_exists(self.client, self.program_id)
        except Exception as e:
            print(f"✗ Fatal: {e}")
            return {}

        for filename in budget_files:
            filepath = self.structured_dir / filename

            if not filepath.exists():
                print(f"⚠ Skipping {filename} - file not found")
                continue

            try:
                print(f"\n=== {filename} ===")
                store = HierarchicalDataStore(str(filepath))
                print(f"Total nodes: {len(store.data)}")

                # Upload all nodes
                mapping = store_all_nodes(self.client, self.payer, store, self.program_id)

                # Save PDA mapping for this file
                pda_file = f"pda_map_{filename}"
                with open(pda_file, 'w') as f:
                    json.dump({k: str(v) for k, v in mapping.items()}, f, indent=2)

                uploaded[filename] = pda_file
                print(f"\n✓ Uploaded {len(mapping)} nodes from {filename}")

            except Exception as e:
                print(f"✗ Failed to upload {filename}: {str(e)}")

        # Save master mapping
        with open(self.mapping_file, 'w') as f:
            json.dump(uploaded, f, indent=2)

        print(f"\n✓ Master mapping saved to {self.mapping_file}")
        print(f"Total files uploaded: {len(uploaded)}")
        return uploaded

    def retrieve_roots(self) -> Dict[str, Dict]:
        """Retrieve root category (00.00) from all uploaded budgets"""
        if not self.mapping_file.exists():
            print("⚠ No accounts found. Run upload_all() first.")
            return {}

        with open(self.mapping_file, 'r') as f:
            uploaded_files = json.load(f)

        roots = {}

        print("\n=== Retrieving root categories ===\n")

        for filename, pda_map_file in uploaded_files.items():
            try:
                # Read the PDA map for this file
                with open(pda_map_file, 'r') as f:
                    pda_map = json.load(f)

                # Get the root node (00.00)
                root_key = "00.00"
                result = read_node_from_chain(self.client, root_key, self.program_id)

                if result:
                    _, root_data = result
                    roots[filename] = {
                        "pda_map_file": pda_map_file,
                        "total_nodes": len(pda_map),
                        "root": {
                            "name": root_data.get("name", "Unknown"),
                            "value": root_data.get("value", 0),
                            "subCategories": root_data.get("subCategories", [])
                        }
                    }
                    print(f"✓ {filename}")
                    print(f"  Name: {roots[filename]['root']['name']}")
                    print(f"  Sub-categories: {len(roots[filename]['root']['subCategories'])}")
                else:
                    print(f"⚠ Root not found for {filename}")

            except Exception as e:
                print(f"✗ Failed to read {filename}: {str(e)}")

        # Save roots data
        roots_file = Path("budget_roots.json")
        with open(roots_file, 'w', encoding='utf-8') as f:
            json.dump(roots, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Roots saved to {roots_file}")
        print(f"Total roots retrieved: {len(roots)}")
        return roots

    def retrieve_category(self, filename: str, category_code: str) -> Optional[Dict]:
        """Retrieve specific category from a budget file"""
        if not self.mapping_file.exists():
            print("⚠ No accounts found. Run upload_all() first.")
            return None

        with open(self.mapping_file, 'r') as f:
            uploaded_files = json.load(f)

        if filename not in uploaded_files:
            print(f"⚠ {filename} not found in uploaded budgets")
            return None

        try:
            result = read_node_from_chain(self.client, category_code, self.program_id)

            if result:
                key, data = result
                return {
                    "filename": filename,
                    "category": category_code,
                    "data": data
                }
            else:
                print(f"⚠ Category {category_code} not found")
                return None

        except Exception as e:
            print(f"✗ Failed to retrieve category: {str(e)}")
            return None

    def print_budget_tree(self, filename: str, start_key: str = "00.00"):
        """Print hierarchical tree view of a budget"""
        print(f"\n=== Tree view: {filename} ===\n")
        print_node_tree(self.client, start_key, self.program_id)

    def export_budget_hierarchy(self, filename: str, start_key: str = "00.00") -> List:
        """Export full hierarchy starting from a node"""
        try:
            hierarchy = traverse_hierarchy(self.client, start_key, self.program_id)
            output_file = f"hierarchy_{filename}"

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(
                    [{"key": k, "data": d} for k, d in hierarchy],
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            print(f"✓ Exported {len(hierarchy)} nodes to {output_file}")
            return hierarchy

        except Exception as e:
            print(f"✗ Failed to export hierarchy: {str(e)}")
            return []

    def list_uploaded_budgets(self) -> Dict:
        """List all uploaded budgets"""
        if not self.mapping_file.exists():
            print("⚠ No budgets uploaded yet")
            return {}

        with open(self.mapping_file, 'r') as f:
            uploaded = json.load(f)

        print("\n=== Uploaded Budgets ===")
        for filename, pda_file in uploaded.items():
            if os.path.exists(pda_file):
                with open(pda_file, 'r') as f:
                    pda_map = json.load(f)
                print(f"{filename} → {len(pda_map)} nodes → {pda_file}")
            else:
                print(f"{filename} → ⚠ PDA map not found")

        return uploaded


if __name__ == "__main__":
    manager = BudgetSolanaManager()

    # Upload all budgets
    print("=== Step 1: Upload ===\n")
    manager.upload_all()

    # Retrieve roots
    print("\n=== Step 2: Retrieve Roots ===\n")
    roots = manager.retrieve_roots()

    # Example: Print tree for first budget
    if roots:
        first_file = list(roots.keys())[0]
        manager.print_budget_tree(first_file)

    print(f"\n✓ Complete: {len(roots)} budgets processed")
