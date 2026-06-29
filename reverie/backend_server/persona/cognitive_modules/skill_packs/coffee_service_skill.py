from persona.cognitive_modules.skill_packs.base import BaseSkillPack
from persona.prompt_template.gpt_structure import get_embedding

class CoffeeServiceSkillPack(BaseSkillPack):
    def __init__(self):
        super().__init__()
        self.name = "coffee_service"
        self.associated_xp = ""

    def can_execute(self, persona, target, maze) -> bool:
        return persona.s_mem.find_nearest_object(target) is not None

    def get_target_tiles(self, persona, target, maze) -> list:
        address = persona.s_mem.find_nearest_object(target)
        if address and address in maze.address_tiles:
            return list(maze.address_tiles[address])
        return []

    def on_arrive(self, persona, target, maze, personas):
        act_desc = persona.scratch.act_description.lower() if persona.scratch.act_description else ""
        
        # 1. Serving Coffee Sync
        if "serving coffee" in act_desc:
            if not getattr(persona.scratch, 'serving_memory_written', False):
                persona.scratch.serving_memory_written = True
                
                # Find customer name dynamically
                customer_name = "Klaus Mueller"
                for p_name in personas:
                    if p_name != persona.name and "klaus" in p_name.lower():
                        customer_name = p_name
                        break
                
                desc = f"{persona.name} served coffee to {customer_name}"
                print(f"=== [协同记忆同步] {persona.name} 到达餐桌，为双方写入‘服务咖啡’记忆 ===")
                
                # Inject to Server (e.g. Isabella)
                is_emb = get_embedding(desc)
                persona.a_mem.add_event(persona.scratch.curr_time, None, 
                                        persona.name, "serve coffee to", customer_name, 
                                        desc, {"serve", "coffee", customer_name.split()[0]}, 5, 
                                        (desc, is_emb), None)
                                        
                # Inject to Customer (e.g. Klaus)
                if customer_name in personas:
                    customer = personas[customer_name]
                    kl_emb = get_embedding(desc)
                    customer.a_mem.add_event(customer.scratch.curr_time, None, 
                                            persona.name, "serve coffee to", customer_name, 
                                            desc, {"serve", "coffee", customer_name.split()[0]}, 5, 
                                            (desc, kl_emb), None)

        # 2. Drinking Coffee Sync
        elif "drinking coffee" in act_desc:
            if not getattr(persona.scratch, 'drinking_memory_written', False):
                persona.scratch.drinking_memory_written = True
                
                # Find server name dynamically
                server_name = "Isabella Rodriguez"
                for p_name in personas:
                    if p_name != persona.name and "isabella" in p_name.lower():
                        server_name = p_name
                        break
                
                desc = f"{persona.name} drank the coffee served by {server_name}"
                print(f"=== [协同记忆同步] {persona.name} 开始饮用咖啡，为双方写入‘饮用咖啡’记忆 ===")
                
                # Inject to Customer (e.g. Klaus)
                kl_emb = get_embedding(desc)
                persona.a_mem.add_event(persona.scratch.curr_time, None, 
                                        persona.name, "drink", "coffee", 
                                        desc, {"drink", "coffee", server_name.split()[0]}, 5, 
                                        (desc, kl_emb), None)
                                        
                # Inject to Server (e.g. Isabella)
                if server_name in personas:
                    server = personas[server_name]
                    is_emb = get_embedding(desc)
                    server.a_mem.add_event(server.scratch.curr_time, None, 
                                            persona.name, "drink", "coffee", 
                                            desc, {"drink", "coffee", server_name.split()[0]}, 5, 
                                            (desc, is_emb), None)
