"""
Clear specific collision tiles in collision_maze.csv to make blocked game objects reachable.

Usage:
    python patch_collision_maze.py --tiles "24,45 25,45" [--dry-run]

The collision_maze.csv is a single-row CSV where values are laid out
in row-major order: index = y * maze_width + x.
Value "0" = passable, any other value (e.g. "32125") = collision block.
"""
import csv, json, os, sys, shutil, argparse
from datetime import datetime

BASE = "/Users/gun/mygame/generative_agents"
MATRIX = os.path.join(BASE, "environment", "frontend_server", "static_dirs", "assets", "the_ville", "matrix")
MAZE_DIR = os.path.join(MATRIX, "maze")
COLLISION_CSV = os.path.join(MAZE_DIR, "collision_maze.csv")

def main():
    parser = argparse.ArgumentParser(description="Clear collision tiles to make game objects reachable.")
    parser.add_argument("--tiles", required=True, help='Space-separated "x,y" pairs to clear. E.g. "24,45 25,45"')
    parser.add_argument("--dry-run", action="store_true", help="Only show what would change, don't write.")
    args = parser.parse_args()

    # Parse tile coords
    tiles_to_clear = []
    for pair in args.tiles.strip().split():
        parts = pair.split(",")
        tiles_to_clear.append((int(parts[0]), int(parts[1])))

    # Load meta
    meta = json.load(open(os.path.join(MATRIX, "maze_meta_info.json")))
    W = int(meta["maze_width"])
    H = int(meta["maze_height"])

    # Read collision CSV
    with open(COLLISION_CSV) as f:
        raw = list(csv.reader(f))[0]

    print(f"地图尺寸: {W} x {H}")
    print(f"碰撞数据长度: {len(raw)} (期望 {W*H})")
    print()

    changes = []
    for x, y in tiles_to_clear:
        idx = y * W + x
        if idx >= len(raw):
            print(f"  ❌ ({x},{y}) 越界 (index={idx})")
            continue
        old_val = raw[idx].strip()
        if old_val == "0":
            print(f"  ⏭️  ({x},{y}) 已经是可通行的 (值=0)，跳过")
            continue
        print(f"  🔧 ({x},{y}) index={idx}: {old_val} → 0 (清除碰撞)")
        changes.append((idx, old_val))
        if not args.dry_run:
            raw[idx] = "0"

    if not changes:
        print("\n没有需要修改的碰撞块。")
        return

    if args.dry_run:
        print(f"\n[DRY RUN] 将修改 {len(changes)} 个碰撞块，但未实际写入。")
        return

    # Backup
    backup_path = COLLISION_CSV + f".bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(COLLISION_CSV, backup_path)
    print(f"\n已备份原文件 → {backup_path}")

    # Write
    with open(COLLISION_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(raw)
    print(f"✅ 已成功清除 {len(changes)} 个碰撞块并写入 collision_maze.csv")

if __name__ == "__main__":
    main()
