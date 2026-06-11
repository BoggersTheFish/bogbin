import sys
import hashlib
from pathlib import Path

def make_bogfs(src_dir_path, dest_file_path):
    src_dir = Path(src_dir_path)
    files = sorted([f for f in src_dir.rglob('*') if f.is_file()])
    
    # Header: Magic "BOGFS\0" (6 bytes) + file count (4 bytes)
    header_magic = b"BOGFS\0"
    file_count = len(files)
    
    # File table entries
    # Each entry: Path (64 bytes), Offset (4 bytes), Length (4 bytes), Hash (32 bytes)
    entry_size = 64 + 4 + 4 + 32
    header_size = len(header_magic) + 4
    file_table_size = file_count * entry_size
    
    current_offset = header_size + file_table_size
    entries = []
    payloads = []
    
    for f in files:
        rel_path = "/" + str(f.relative_to(src_dir))
        content = f.read_bytes()
        length = len(content)
        h = hashlib.sha256(content).digest()
        
        # Path padded/truncated to 64 bytes
        path_bytes = rel_path.encode('utf-8')[:63]
        path_padded = path_bytes + b'\0' * (64 - len(path_bytes))
        
        entries.append({
            "path": path_padded,
            "offset": current_offset,
            "length": length,
            "hash": h
        })
        payloads.append(content)
        current_offset += length
        
    with open(dest_file_path, "wb") as out:
        out.write(header_magic)
        out.write(file_count.to_bytes(4, byteorder='big'))
        
        for entry in entries:
            out.write(entry["path"])
            out.write(entry["offset"].to_bytes(4, byteorder='big'))
            out.write(entry["length"].to_bytes(4, byteorder='big'))
            out.write(entry["hash"])
            
        for payload in payloads:
            out.write(payload)
            
    print(f"Packed {file_count} files into {dest_file_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 make_bogfs.py <src_dir> <dest_file>")
        sys.exit(1)
    make_bogfs(sys.argv[1], sys.argv[2])
