# python
import base64
import hashlib
import json
import os
from typing import Dict, Tuple, Optional, List, Any, Set

from solana.rpc.api import Client
from solders.pubkey import Pubkey
import borsh_construct as borsh

# -------- Config --------
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
PROGRAM_ID = Pubkey.from_string(os.getenv("PROGRAM_ID", "GDMu4vZGC87ER1BNJqTr7ecJE2hXz47WATZFrBD44mB6"))

# -------- Anchor helpers --------
def anchor_account_discriminator(name: str) -> bytes:
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]

NODE_ACCOUNT_DISC = anchor_account_discriminator("NodeAccount")

# -------- PDA --------
def derive_node_pda(key: str, program_id: Pubkey) -> Tuple[Pubkey, int]:
    return Pubkey.find_program_address([b"node", key.encode("utf-8")], program_id)

# -------- Account schema (Anchor-compatible) --------
# Anchor encodes String as length-prefixed UTF-8, and Vec<u8> as length-prefixed bytes
node_account_schema = borsh.CStruct(
    "key" / borsh.String,
    "data" / borsh.Vec(borsh.U8),
    "bump" / borsh.U8,
)

def _extract_raw_data_from_account(account: Any) -> Optional[bytes]:
    """
    Robustly extract raw account bytes from RPC account object.
    Ensures base64 decoding and returns None when not available.
    """
    if account is None:
        return None

    # Ensure the account belongs to our program
    try:
        if str(account.owner) != str(PROGRAM_ID):
            return None
    except Exception:
        # If owner is not accessible in typed form, try dict fallback
        owner = None
        try:
            owner = account["owner"]
        except Exception:
            pass
        if owner and owner != str(PROGRAM_ID):
            return None

    data_field = None
    try:
        data_field = account.data  # solders typed
    except Exception:
        try:
            data_field = account["data"]  # dict/JSON fallback
        except Exception:
            return None

    # Possible shapes:
    # - bytes / bytearray
    # - [base64_string, "base64"]
    # - {"data": [base64_string, "base64"], ...}
    if isinstance(data_field, (bytes, bytearray)):
        return bytes(data_field)

    if isinstance(data_field, (list, tuple)) and len(data_field) >= 2:
        b64_str, enc = data_field[0], data_field[1]
        if enc == "base64":
            return base64.b64decode(b64_str)
        return None

    # Some typed wrappers expose .data.data or similar; best-effort
    try:
        inner = getattr(data_field, "data", None)
        enc = getattr(data_field, "encoding", "base64")
        if inner and enc == "base64":
            return base64.b64decode(inner)
    except Exception:
        pass

    return None

def deserialize_node_data(raw: bytes) -> Tuple[str, Dict]:
    """
    Deserialize on-chain node account data:
    [8 bytes discriminator][String key][Vec<u8> data][u8 bump]
    """
    if raw is None or len(raw) < 8:
        raise ValueError("Account data too short")

    if raw[:8] != NODE_ACCOUNT_DISC:
        raise ValueError("Account discriminator mismatch")

    body = raw[8:]
    parsed = node_account_schema.parse(body)
    key = parsed.key
    json_data = json.loads(bytes(parsed.data).decode("utf-8"))
    return key, json_data

# -------- Read Functions --------
def read_node_from_chain(client: Client, key: str, program_id: Pubkey) -> Optional[Tuple[str, Dict]]:
    """Read a single node from on-chain storage. Returns None if not found or not our account."""
    pda, _ = derive_node_pda(key, program_id)
    try:
        # Force base64 encoding to simplify extraction
        info = client.get_account_info(pda, encoding="base64")
        account = info.value
        if not account:
            return None

        raw = _extract_raw_data_from_account(account)
        if not raw:
            return None

        return deserialize_node_data(raw)
    except Exception as e:
        print(f"Error reading {key}: {e}")
        return None

def read_all_nodes(client: Client, keys: List[str], program_id: Pubkey) -> Dict[str, Dict]:
    """Read multiple nodes from chain. Individual failures are logged but don't stop processing."""
    results: Dict[str, Dict] = {}
    for key in keys:
        data = read_node_from_chain(client, key, program_id)
        if data:
            _, node_data = data
            results[key] = node_data
    return results

def traverse_hierarchy(client: Client, start_key: str, program_id: Pubkey) -> List[Tuple[str, Dict]]:
    """Traverse hierarchy from start_key. Uses BFS to avoid deep recursion."""
    results: List[Tuple[str, Dict]] = []
    queue: List[str] = [start_key]
    visited: Set[str] = set()

    while queue:
        current_key = queue.pop(0)
        if current_key in visited:
            continue
        visited.add(current_key)

        data = read_node_from_chain(client, current_key, program_id)
        if data:
            key, node_data = data
            results.append((key, node_data))
            # Extend queue with subcategories if present
            sub_cats = node_data.get("subCategories", [])
            if sub_cats:
                queue.extend(sub_cats)

    return results

def print_node_tree(client: Client, start_key: str, program_id: Pubkey, indent: int = 0):
    data = read_node_from_chain(client, start_key, program_id)
    if not data:
        print(f"{'  ' * indent}❌ {start_key} (not found)")
        return

    key, node_data = data
    name = node_data.get("name", "Unknown")
    value = node_data.get("value", "")
    value_str = f" = {value}" if value else ""
    print(f"{'  ' * indent}📦 {key}: {name}{value_str}")

    for sub_key in node_data.get("subCategories", []):
        print_node_tree(client, sub_key, program_id, indent + 1)

def _load_candidate_keys() -> List[str]:
    # Prefer PDA map if present
    pda_map_file = "../solana_pda_map.json"
    if os.path.exists(pda_map_file):
        with open(pda_map_file, "r") as f:
            pda_map = json.load(f)
        return list(pda_map.keys())

    # Fallback to original JSON
    json_file = "../structured_output/SECTIUNEA_TOTAL_anexa_4_structured_with_roots.json"
    if os.path.exists(json_file):
        with open(json_file, "r") as f:
            data = json.load(f)
        return list(data.keys())

    return []

def main():
    print("=== Reading Data from Solana Chain ===\n")

    client = Client(RPC_URL)
    print(f"RPC: {RPC_URL}")
    print(f"Program: {PROGRAM_ID}\n")

    keys = _load_candidate_keys()
    if not keys:
        print("No keys found. Provide PDA map or source JSON.")
        return
    print(f"Found {len(keys)} keys to probe\n")

    # Example 1: Read a single node
    print("=== Example 1: Read Single Node ===")
    test_key = "00.01"
    result = read_node_from_chain(client, test_key, PROGRAM_ID)
    if result:
        key, data = result
        pda, _ = derive_node_pda(key, PROGRAM_ID)
        print(f"Key: {key}")
        print(f"PDA: {pda}")
        print(f"Data: {json.dumps(data, indent=2)}\n")
    else:
        print(f"Node '{test_key}' not found on chain\n")

    # Example 2: Read multiple nodes
    print("=== Example 2: Read Multiple Nodes ===")
    sample_keys = keys[:5]
    all_data = read_all_nodes(client, sample_keys, PROGRAM_ID)
    for k, data in all_data.items():
        print(f"{k}: {data.get('name', 'Unknown')}")
    print()

    # Example 3: Traverse hierarchy
    print("=== Example 3: Traverse Hierarchy ===")
    root_key = "00.00"
    hierarchy = traverse_hierarchy(client, root_key, PROGRAM_ID)
    print(f"Found {len(hierarchy)} nodes in hierarchy starting from '{root_key}'\n")

    # Example 4: Print as tree
    print("=== Example 4: Tree View ===")
    print_node_tree(client, root_key, PROGRAM_ID)
    print()

    # Example 5: Export all data to JSON
    print("=== Example 5: Export All Data ===")
    all_chain_data = read_all_nodes(client, keys, PROGRAM_ID)
    output_file = "../chain_data_export.json"
    with open(output_file, "w") as f:
        json.dump(all_chain_data, f, indent=2)
    print(f"✓ Exported {len(all_chain_data)} nodes to {output_file}")

if __name__ == "__main__":
    main()
