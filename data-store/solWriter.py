# python
# file: data-store/solWriter.py
import base64
import json
import os
import struct
import hashlib
from typing import Dict, List, Tuple, Optional, Any

from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.message import Message
from solders.system_program import ID as SYSTEM_PROGRAM_ID
import borsh_construct as borsh

# -------- Config --------
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
PROGRAM_KEYPAIR_PATH = os.getenv("ANCHOR_PROGRAM_KEYPAIR", "target/deploy/data_store-keypair.json")

def load_program_id() -> Pubkey:
    env_pid = os.getenv("PROGRAM_ID")
    if env_pid:
        return Pubkey.from_string(env_pid)
    try:
        with open(PROGRAM_KEYPAIR_PATH, "r") as f:
            kp_bytes = bytes(json.load(f))
        return Keypair.from_bytes(kp_bytes).pubkey()
    except FileNotFoundError:
        raise RuntimeError(
            f"Program ID file `{PROGRAM_KEYPAIR_PATH}` not found. "
            f"Set env PROGRAM_ID to your deployed devnet program public key."
        )

PROGRAM_ID = load_program_id()

# -------- Anchor discriminators --------
def anchor_method_discriminator(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]

def anchor_account_discriminator(name: str) -> bytes:
    return hashlib.sha256(f"account:{name}".encode()).digest()[:8]

NODE_ACCOUNT_DISC = anchor_account_discriminator("NodeAccount")

# -------- Account schemas (v1 and v2 tolerant) --------
# v1: struct { key: String, data: Vec<u8>, bump: u8 }
node_account_v1_schema = borsh.CStruct(
    "key" / borsh.String,
    "data" / borsh.Vec(borsh.U8),
    "bump" / borsh.U8,
)
# v2: struct { key: String, capacity: u32, data: Vec<u8>, bump: u8 }
node_account_v2_schema = borsh.CStruct(
    "key" / borsh.String,
    "capacity" / borsh.U32,
    "data" / borsh.Vec(borsh.U8),
    "bump" / borsh.U8,
)

# -------- PDA --------
def derive_node_pda(key: str, program_id: Pubkey) -> Tuple[Pubkey, int]:
    return Pubkey.find_program_address([b"node", key.encode("utf-8")], program_id)

# -------- Serialize --------
def serialize_node_data(_: str, data: Dict) -> bytes:
    return json.dumps(data, sort_keys=True).encode("utf-8")

# -------- Robust account data extraction --------
def _extract_raw_data_from_account(account: Any) -> Optional[bytes]:
    if account is None:
        return None
    # owner filter (only our program)
    try:
        if str(account.owner) != str(PROGRAM_ID):
            return None
    except Exception:
        try:
            if account["owner"] != str(PROGRAM_ID):
                return None
        except Exception:
            pass

    data_field = None
    try:
        data_field = account.data  # typed
    except Exception:
        try:
            data_field = account["data"]  # dict
        except Exception:
            return None

    if isinstance(data_field, (bytes, bytearray)):
        return bytes(data_field)

    if isinstance(data_field, (list, tuple)) and len(data_field) >= 2:
        b64_str, enc = data_field[0], data_field[1]
        if enc == "base64":
            return base64.b64decode(b64_str)
        return None

    try:
        inner = getattr(data_field, "data", None)
        enc = getattr(data_field, "encoding", "base64")
        if inner and enc == "base64":
            return base64.b64decode(inner)
    except Exception:
        pass

    return None

def _get_node_capacity(client: Client, node_pda: Pubkey) -> Optional[int]:
    """
    Return capacity if account is v2; if v1, return current data length.
    On any parse error, return None.
    """
    try:
        info = client.get_account_info(node_pda, encoding="base64")
        acc = info.value
        if not acc:
            return None
        raw = _extract_raw_data_from_account(acc)
        if not raw or len(raw) < 8 or raw[:8] != NODE_ACCOUNT_DISC:
            return None
        body = raw[8:]

        # Try v2 first
        try:
            parsed_v2 = node_account_v2_schema.parse(body)
            return int(parsed_v2.capacity)
        except Exception:
            pass

        # Fallback to v1
        try:
            parsed_v1 = node_account_v1_schema.parse(body)
            return int(len(parsed_v1.data))
        except Exception:
            return None
    except Exception:
        return None

# -------- Error helpers --------
def _is_fallback_not_found(err: Exception) -> bool:
    s = str(err)
    return (
        "InstructionFallbackNotFound" in s
        or "Fallback functions are not supported" in s
        or "custom program error: 0x65" in s
        or "Custom(101)" in s
        or "custom(101)" in s
    )

def _is_data_too_large(err: Exception) -> bool:
    s = str(err)
    return (
        "DataTooLarge" in s
        or "custom program error: 0x1770" in s
        or "Custom(6000)" in s
        or "custom(6000)" in s
    )

# -------- Instructions --------
def build_initialize_node_ix(program_id: Pubkey, payer: Pubkey, node_pda: Pubkey, key: str, data_len: int) -> Instruction:
    disc = anchor_method_discriminator("initialize_node")
    key_bytes = key.encode("utf-8")
    ix_data = disc + struct.pack("<I", len(key_bytes)) + key_bytes + struct.pack("<I", data_len)
    accounts = [
        AccountMeta(node_pda, False, True),
        AccountMeta(payer, True, True),
        AccountMeta(SYSTEM_PROGRAM_ID, False, False),
    ]
    return Instruction(program_id, ix_data, accounts)

def build_resize_node_ix(program_id: Pubkey, payer: Pubkey, node_pda: Pubkey, key: str, new_len: int) -> Instruction:
    # Requires on-chain `resize_node(key: String, new_len: u32)`
    disc = anchor_method_discriminator("resize_node")
    key_bytes = key.encode("utf-8")
    ix_data = disc + struct.pack("<I", len(key_bytes)) + key_bytes + struct.pack("<I", new_len)
    accounts = [
        AccountMeta(node_pda, False, True),
        AccountMeta(payer, True, True),
        AccountMeta(SYSTEM_PROGRAM_ID, False, False),
    ]
    return Instruction(program_id, ix_data, accounts)

def build_store_node_ix(program_id: Pubkey, node_pda: Pubkey, key: str, data_bytes: bytes) -> Instruction:
    disc = anchor_method_discriminator("store_node")
    key_bytes = key.encode("utf-8")
    ix_data = disc + struct.pack("<I", len(key_bytes)) + key_bytes + struct.pack("<I", len(data_bytes)) + data_bytes
    accounts = [AccountMeta(node_pda, False, True)]
    return Instruction(program_id, ix_data, accounts)

# -------- Tx helper --------
def _send_ix(client: Client, payer: Keypair, ix: Instruction):
    recent_blockhash = client.get_latest_blockhash().value.blockhash
    msg = Message.new_with_blockhash([ix], payer.pubkey(), recent_blockhash)
    tx = Transaction([payer], msg, recent_blockhash)
    sig = client.send_transaction(tx, opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed))
    client.confirm_transaction(sig.value, commitment=Confirmed)

# -------- Storage Functions --------
def store_node_on_chain(client: Client, payer: Keypair, key: str, data: Dict, program_id: Pubkey) -> Pubkey:
    node_pda, _ = derive_node_pda(key, program_id)
    account_info = client.get_account_info(node_pda, encoding="base64")
    account_exists = account_info.value is not None

    data_bytes = serialize_node_data(key, data)

    if not account_exists:
        init_ix = build_initialize_node_ix(program_id, payer.pubkey(), node_pda, key, len(data_bytes))
        _send_ix(client, payer, init_ix)
    else:
        capacity = _get_node_capacity(client, node_pda)
        # Only resize if capacity is known and significantly different to reduce operations
        if capacity is not None and len(data_bytes) != capacity:
            try:
                resize_ix = build_resize_node_ix(program_id, payer.pubkey(), node_pda, key, len(data_bytes))
                _send_ix(client, payer, resize_ix)
            except Exception as e:
                if _is_fallback_not_found(e):
                    # Pad data to match capacity to avoid resize
                    if len(data_bytes) < capacity:
                        data_bytes = data_bytes.ljust(capacity, b'\0')
                    # If data is larger, we'll try to store anyway and let it fail if needed
                else:
                    raise

    store_ix = build_store_node_ix(program_id, node_pda, key, data_bytes)
    _send_ix(client, payer, store_ix)
    return node_pda


def read_node_from_chain(client: Client, key: str, program_id: Pubkey) -> Tuple[str, Dict]:
    pda, _ = derive_node_pda(key, program_id)
    info = client.get_account_info(pda, encoding="base64")
    if not info.value:
        raise ValueError(f"Node '{key}' not found")
    raw = _extract_raw_data_from_account(info.value)
    if not raw or raw[:8] != NODE_ACCOUNT_DISC:
        raise ValueError(f"Node '{key}' malformed or not owned by program")
    body = raw[8:]

    # Try v2 then v1
    try:
        parsed_v2 = node_account_v2_schema.parse(body)
        return parsed_v2.key, json.loads(bytes(parsed_v2.data).decode("utf-8"))
    except Exception:
        pass

    try:
        parsed_v1 = node_account_v1_schema.parse(body)
        return parsed_v1.key, json.loads(bytes(parsed_v1.data).decode("utf-8"))
    except Exception:
        raise ValueError(f"Node '{key}' parse failed")

# -------- Utility --------
def load_keypair() -> Keypair:
    path = os.getenv("SOLANA_KEYPAIR_PATH", os.path.expanduser("~/.config/solana/id.json"))
    with open(path, "r") as f:
        secret = json.load(f)
    return Keypair.from_bytes(bytes(secret))

class HierarchicalDataStore:
    def __init__(self, path: str):
        with open(path, "r") as f:
            self.data: Dict = json.load(f)
    def get_all_keys(self) -> List[str]:
        return sorted(self.data.keys())
    def traverse_path(self, start: str) -> List[str]:
        path, queue = [], [start]
        while queue:
            cur = queue.pop(0)
            if cur not in self.data:
                continue
            path.append(cur)
            queue.extend(self.data[cur].get("subCategories", []))
        return path

def ensure_program_exists(client: Client, program_id: Pubkey):
    info = client.get_account_info(program_id)
    if not info.value:
        raise RuntimeError(f"Program {program_id} not found on RPC {RPC_URL}.")

def ensure_rpc_available(url: str):
    test_client = Client(url)
    test_client.get_version()

def store_all_nodes(client: Client, payer: Keypair, store: HierarchicalDataStore, program_id: Pubkey) -> Dict[str, Pubkey]:
    mapping = {}
    keys = store.get_all_keys()
    for i, key in enumerate(keys, 1):
        data = store.data[key]
        print(f"[{i}/{len(keys)}] Storing {key}...", end=" ", flush=True)
        try:
            pda = store_node_on_chain(client, payer, key, data, program_id)
            mapping[key] = pda
            print(f"✓ {pda}")
        except Exception as e:
            print(f"✗ Error: {e}")
    return mapping

def main():
    print("=== Storing Full JSON (PDA Approach) ===\n")
    json_file = "../structured_output/SECTIUNEA_TOTAL_anexa_2_structured_with_roots.json"
    if not os.path.exists(json_file):
        print(f"Error: JSON file not found at {json_file}")
        return

    store = HierarchicalDataStore(json_file)
    print(f"Total nodes to store: {len(store.data)}\n")

    try:
        ensure_rpc_available(RPC_URL)
    except Exception as e:
        print(f"Fatal: {e}")
        return

    client = Client(RPC_URL)
    payer = load_keypair()

    try:
        bal = client.get_balance(payer.pubkey()).value
    except Exception as e:
        print(f"Fatal balance fetch error: {e}")
        return

    print(f"RPC: {RPC_URL}")
    print(f"Payer: {payer.pubkey()}")
    print(f"Balance: {bal / 1e9:.4f} SOL")
    print(f"Program: {PROGRAM_ID}\n")

    try:
        ensure_program_exists(client, PROGRAM_ID)
    except Exception as e:
        print(f"Fatal: {e}")
        return

    print("Storing nodes...\n")
    mapping = store_all_nodes(client, payer, store, PROGRAM_ID)

    out_file = "../solana_pda_map.json"
    with open(out_file, "w") as f:
        json.dump({k: str(v) for k, v in mapping.items()}, f, indent=2)
    print(f"\n✓ PDA mapping saved to {out_file}\n")

    print("=== Sample Reads ===\n")
    path = store.traverse_path("00.00")
    for key in path[:5]:
        try:
            k, data = read_node_from_chain(client, key, PROGRAM_ID)
            pda, _ = derive_node_pda(key, PROGRAM_ID)
            print(f"{k} -> {pda}")
        except Exception as e:
            print(f"Read {key}: {e}")
    print(f"\nTraversal size: {len(path)}")

if __name__ == "__main__":
    main()
