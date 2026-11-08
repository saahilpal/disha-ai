import time, json, os

jsonl_path = "audit/simulations/meera_15min_full.jsonl"
print("Monitoring Meera simulation...")

while True:
    if os.path.exists(jsonl_path):
        with open(jsonl_path, "r") as f:
            lines = f.readlines()
        print(f"Current turns recorded: {len(lines)}")
        if len(lines) > 0:
            try:
                last_turn = json.loads(lines[-1].strip())
                print(f"Turn {last_turn.get('turn')}: {last_turn.get('user', '')[:40]}... -> Disha: {last_turn.get('disha', '')[:60]}...")
            except Exception as e:
                print("Error parsing last line:", e)
    else:
        print("Waiting for jsonl file to appear...")
    time.sleep(30)
