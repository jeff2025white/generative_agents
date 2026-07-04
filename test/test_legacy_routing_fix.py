
import sys
import os
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).parent.parent
sys.path.append(str(root / "reverie" / "backend_server"))

from persona.prompt_template.gpt_structure import ChatGPT_single_request, _resolve_request_config
from llm_api_config import get_default_cloud_chat_request_config

def test_legacy_routing():
    print("Testing legacy routing fallback...")
    
    # 1. Check if _resolve_request_config returns cloud default
    cloud_default = get_default_cloud_chat_request_config()
    resolved = _resolve_request_config()
    
    print(f"Cloud Default: {cloud_default['model']}")
    print(f"Resolved Default: {resolved['model']}")
    
    assert resolved['model'] == cloud_default['model'], "Fallback should be cloud default"
    assert resolved['api_base'] == cloud_default['api_base'], "Fallback should use cloud API base"
    
    print("SUCCESS: Legacy routing now falls back to cloud defaults.")

if __name__ == "__main__":
    try:
        test_legacy_routing()
    except Exception as e:
        print(f"FAILURE: {e}")
        sys.exit(1)
