import json
import os
import re
from collections import defaultdict

def parse_logs():
    # Directories and files
    logs_dir = "logs"
    sim_log_path = os.path.join(logs_dir, "sim_20260711_213317.log")
    dialogue_path = os.path.join(logs_dir, "social_dialogue_trace.jsonl")
    motive_path = os.path.join(logs_dir, "motive_monitor.jsonl")
    outcome_path = os.path.join(logs_dir, "action_outcome.jsonl")
    exec_debug_path = os.path.join(logs_dir, "action_execution_debug.jsonl")

    # Timeline dictionary: persona -> step -> dict of event info
    timeline = defaultdict(lambda: defaultdict(lambda: {
        "decisions": [],
        "motives": None,
        "outcomes": [],
        "dialogues": [],
        "exec_events": [],
        "sim_time": None
    }))

    # 1. Parse sim_log_path for Decisions and Step timings/times
    if os.path.exists(sim_log_path):
        with open(sim_log_path, "r", encoding="utf-8") as f:
            curr_step = None
            curr_time = None
            for line in f:
                # Find step markers: 📍 Step 1 | 🕐 2026-07-11 08:00:10
                step_m = re.search(r'📍 Step (\d+)\s*\|\s*🕐 ([\d\-\s:]+)', line)
                if step_m:
                    curr_step = int(step_m.group(1))
                    curr_time = step_m.group(2).strip()
                    continue
                
                # Check for decisions: [Persona] 决策输出: '...'
                dec_m = re.search(r'\[([^\]]+)\] 决策输出:\s*\'([^\']+)\'', line)
                if dec_m and curr_step is not None:
                    name = dec_m.group(1).strip()
                    decision_text = dec_m.group(2).strip()
                    timeline[name][curr_step]["decisions"].append(decision_text)
                    if not timeline[name][curr_step]["sim_time"]:
                        timeline[name][curr_step]["sim_time"] = curr_time

    # Helper to load JSONL safely
    def load_jsonl(path):
        if not os.path.exists(path):
            return []
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        return records

    # 2. Parse dialogues
    for r in load_jsonl(dialogue_path):
        step = r.get("curr_step")
        persona = r.get("persona")
        partner = r.get("partner_name")
        sim_time = r.get("sim_time")
        if step is not None and persona:
            timeline[persona][step]["dialogues"].append({
                "partner": partner,
                "summary": r.get("convo_summary"),
                "topic": r.get("dialogue_topic"),
                "transcript": r.get("transcript_text")
            })
            if partner:
                # Also index it for partner if not already there
                timeline[partner][step]["dialogues"].append({
                    "partner": persona,
                    "summary": r.get("convo_summary"),
                    "topic": r.get("dialogue_topic"),
                    "transcript": r.get("transcript_text")
                })
            if sim_time:
                timeline[persona][step]["sim_time"] = sim_time
                if partner:
                    timeline[partner][step]["sim_time"] = sim_time

    # 3. Parse motives
    for r in load_jsonl(motive_path):
        step = r.get("curr_step")
        persona = r.get("persona")
        sim_time = r.get("sim_time")
        if step is not None and persona:
            # We can take the last motive update of this step
            timeline[persona][step]["motives"] = {
                "dominant": r.get("dominant_motive"),
                "secondary": r.get("secondary_motive"),
                "sentence": r.get("motive_sentence"),
                "top_scores": r.get("top_scores")
            }
            if sim_time:
                timeline[persona][step]["sim_time"] = sim_time

    # 4. Parse outcomes
    for r in load_jsonl(outcome_path):
        step = r.get("curr_step")
        persona = r.get("persona")
        sim_time = r.get("sim_time")
        outcome = r.get("outcome") or {}
        if step is not None and persona:
            action = outcome.get("action") or {}
            execution = outcome.get("execution") or {}
            effects = outcome.get("effects") or {}
            timeline[persona][step]["outcomes"].append({
                "detail": action.get("detail"),
                "skill_id": action.get("skill_id"),
                "target": action.get("target"),
                "result": execution.get("result"),
                "reason": execution.get("reason"),
                "effects": effects.get("self_attribute_effects")
            })
            if sim_time:
                timeline[persona][step]["sim_time"] = sim_time

    # 5. Parse exec debug
    for r in load_jsonl(exec_debug_path):
        step = r.get("curr_step")
        persona = r.get("persona")
        sim_time = r.get("sim_time")
        event = r.get("event")
        if step is not None and persona:
            timeline[persona][step]["exec_events"].append({
                "event": event,
                "description": r.get("act_description"),
                "reason": r.get("blocked_reason") or r.get("precheck_result", {}).get("reason")
            })
            if sim_time:
                timeline[persona][step]["sim_time"] = sim_time

    # Now let's generate the markdown report!
    personas = sorted(list(timeline.keys()))
    
    out = []
    out.append("# NPC Timeline Analysis Report")
    out.append("\nThis report aggregates simulation logs from run `sim_20260711_213317`, compiling individual NPC timelines, decisions, motives, dialogues, and action outcomes.")
    
    for p in personas:
        out.append(f"\n## NPC: {p}")
        steps = sorted(list(timeline[p].keys()))
        
        # Keep track of active statuses to avoid redundant prints
        last_decision = None
        
        for step in steps:
            data = timeline[p][step]
            sim_time = data["sim_time"] or f"Step {step}"
            
            # Print state if there are decisions, dialogue, outcomes, or motive details
            has_major_event = bool(data["decisions"] or data["dialogues"] or data["outcomes"] or 
                                 any(ev["event"] in ["arrive", "skill_blocked"] for ev in data["exec_events"]))
            
            if not has_major_event:
                continue
                
            out.append(f"\n### Step {step} | {sim_time}")
            
            # Motives
            if data["motives"]:
                m = data["motives"]
                m_str = f"**Motives**: Dominant: *{m['dominant']}*, Secondary: *{m['secondary']}*"
                if m["sentence"]:
                    m_str += f" — \"{m['sentence']}\""
                out.append(f"- {m_str}")
                
            # Decisions
            for dec in data["decisions"]:
                out.append(f"- **Decision**: \"{dec}\"")
                
            # Dialogue
            for dlg in data["dialogues"]:
                out.append(f"- **Conversation with {dlg['partner']}** on topic: *{dlg['topic']}*")
                out.append(f"  - *Summary*: {dlg['summary']}")
                # Format transcript indented
                trans = dlg['transcript'].replace('\n', '\n    > ')
                out.append(f"  - *Transcript*:\n    > {trans}")
                
            # Action Exec / Outcomes
            for out_evt in data["outcomes"]:
                eff_str = ""
                if out_evt["effects"]:
                    nonzero_effects = {k: v for k, v in out_evt["effects"].items() if v != 0.0}
                    if nonzero_effects:
                        eff_str = f" (Effects: {nonzero_effects})"
                
                reason_str = f" (Reason: {out_evt['reason']})" if out_evt['reason'] else ""
                out.append(f"- **Action Outcome**: {out_evt['detail']} [{out_evt['skill_id']}] -> **{out_evt['result']}**{reason_str}{eff_str}")
                
            # Significant path events
            for ev in data["exec_events"]:
                if ev["event"] == "arrive":
                    out.append(f"- **Movement**: Arrived at target destination (*{ev['description']}*).")
                elif ev["event"] == "skill_blocked":
                    out.append(f"- **Execution Blocked**: Blocked on action (*{ev['description']}*) due to: `{ev['reason']}`.")

    # Write to output file
    output_report_path = "scratch/timeline_summary.md"
    os.makedirs(os.path.dirname(output_report_path), exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"Report written to {output_report_path}")

if __name__ == '__main__':
    parse_logs()
