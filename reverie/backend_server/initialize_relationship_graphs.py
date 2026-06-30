import os
import sys
import json

# Ensure project path is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import openai_api_base, gpt35_model, openai_api_key
import openai

openai.api_key = openai_api_key
if openai_api_base:
    openai.api_base = openai_api_base

def analyze_relationship_with_llm(persona_name, target_name, memories):
    """
    Call Ollama to analyze relationship type and trust score based on memories.
    """
    if not memories:
        return {"relationship": "stranger", "trust": 0.5, "recent_events": []}
    
    mem_text = "\n".join([f"- {m}" for m in memories[:10]])
    prompt = (
        f"You are a relationship analysis expert. Analyze the relationship from {persona_name}'s perspective "
        f"towards {target_name} based on the following memory fragments:\n"
        f"\"\"\"\n{mem_text}\n\"\"\"\n\n"
        f"Tasks:\n"
        f"1. Determine the relationship type (e.g. friend, colleague, acquaintance, enemy, stranger).\n"
        f"2. Rate the trust score between 0.0 and 1.0.\n"
        f"3. Summarize the 3 most representative recent interactions in English.\n\n"
        f"Respond ONLY with a valid JSON object in this format:\n"
        f'{{"relationship": "friend", "trust": 0.8, "recent_events": ["shared coffee at cafe", "talked about project"]}}'
    )
    
    try:
        response = openai.ChatCompletion.create(
            model=gpt35_model,
            messages=[
                {"role": "system", "content": "You are a precise data analysis assistant. You output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=200
        )
        resp_text = response["choices"][0]["message"]["content"].strip()
        
        # Clean up code blocks if LLM wraps in markdown
        if "```" in resp_text:
            resp_text = resp_text.split("```")[1]
            if resp_text.startswith("json"):
                resp_text = resp_text[4:]
        
        data = json.loads(resp_text)
        # Validate data structure
        if "relationship" in data and "trust" in data:
            data["trust"] = max(0.0, min(1.0, float(data["trust"])))
            return data
    except Exception as e:
        print(f"  [LLM 提取错误] 分析 {persona_name} -> {target_name} 失败: {e}")
    
    # Fallback to rule-based analysis
    count = len(memories)
    trust = max(0.5, min(0.9, 0.5 + count * 0.03))
    rel_type = "friend" if count > 5 else "acquaintance"
    recent = memories[:3]
    return {
        "relationship": rel_type,
        "trust": trust,
        "recent_events": recent
    }

def run_migration(sim_dir):
    print(f"=== 开始扫描并整理关系图谱，目标目录: {sim_dir} ===")
    
    personas_dir = os.path.join(sim_dir, "personas")
    if not os.path.exists(personas_dir):
        print(f"错误: 找不到 personas 目录: {personas_dir}")
        return
        
    persona_names = [d for d in os.listdir(personas_dir) if os.path.isdir(os.path.join(personas_dir, d))]
    print(f"找到 NPC 列表: {persona_names}")
    
    for p_name in persona_names:
        print(f"\n正在处理 NPC: {p_name}")
        a_mem_dir = os.path.join(personas_dir, p_name, "bootstrap_memory", "associative_memory")
        nodes_path = os.path.join(a_mem_dir, "nodes.json")
        graph_path = os.path.join(a_mem_dir, "social_relationship_graph.json")
        
        if not os.path.exists(nodes_path):
            print(f"  警告: 找不到 nodes.json: {nodes_path}，跳过该角色。")
            continue
            
        with open(nodes_path, "r", encoding="utf-8") as f:
            nodes = json.load(f)
            
        relations = {}
        
        # Analyze other NPCs
        for target_name in persona_names:
            if target_name == p_name:
                continue
                
            first_name = target_name.split()[0]
            target_memories = []
            
            # Scan memory nodes for mentions of target
            sorted_nodes = sorted(nodes.values(), key=lambda x: x.get("node_count", 0), reverse=True)
            
            for node in sorted_nodes:
                desc = node.get("description", "")
                subj = node.get("subject", "")
                obj = node.get("object", "")
                
                # Broad matching: if description mentions the target name, or subject/object relates to the target
                if (first_name in desc or target_name in desc) and node.get("type") in ["event", "chat"]:
                    target_memories.append(desc)
            
            if target_memories:
                print(f"  发现与 {target_name} 的记忆碎片数量: {len(target_memories)}。正在通过大模型整理...")
                rel_info = analyze_relationship_with_llm(p_name, target_name, target_memories)
                relations[target_name] = rel_info
                print(f"  -> 提炼结果: 关系={rel_info['relationship']}, 信任度={rel_info['trust']:.2f}")
                
        # Write social_relationship_graph.json
        graph_data = {"relations": relations}
        with open(graph_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)
        print(f"  成功为 {p_name} 写入关系图谱: {graph_path}")
        
    print("\n=== 关系图谱整理完成！ ===")

if __name__ == "__main__":
    # 默认整理项目基础模板: base_the_ville_isabella_maria_klaus
    default_sim = "g:/generative_agents/environment/frontend_server/storage/base_the_ville_isabella_maria_klaus"
    
    # 也可以从命令行参数传入其他项目目录
    if len(sys.argv) > 1:
        target_sim = sys.argv[1]
    else:
        target_sim = default_sim
        
    run_migration(target_sim)
