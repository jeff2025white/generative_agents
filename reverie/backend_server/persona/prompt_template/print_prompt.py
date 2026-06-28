"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: print_prompt.py
Description: For printing prompts when the setting for verbose is set to True.
"""
import sys
sys.path.append('../')

import json
import numpy
import datetime
import random

from global_methods import *
from persona.prompt_template.gpt_structure import *
from utils import *

##############################################################################
#                    PERSONA Chapter 1: Prompt Structures                    #
##############################################################################

def print_run_prompts(prompt_template=None, 
                      persona=None, 
                      gpt_param=None, 
                      prompt_input=None,
                      prompt=None, 
                      output=None): 
  print (f"=== 提示词模板：{prompt_template}")
  print ("~~~ 智能体人物 (persona)   -------------------------------------------")
  print (persona.name, "\n")
  print ("~~~ GPT 模型参数 (gpt_param) -----------------------------------------")
  print (gpt_param, "\n")
  print ("~~~ 提示词输入参数 (prompt_input)   ----------------------------------")
  print (prompt_input, "\n")
  print ("~~~ 最终拼装提示词 (prompt)   ----------------------------------------")
  print (prompt, "\n")
  print ("~~~ 语言模型输出 (output)   ------------------------------------------")
  print (output, "\n") 
  print ("=== 结束 (END) ===================================================")
  print ("\n\n\n")

  # Add agent-specific logging to prevent multi-threading interleaving
  import os
  import sys
  try:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Extract sim_code from sys.argv if available to log in run-specific directory
    sim_code = "general"
    if len(sys.argv) >= 3:
      sim_code = sys.argv[2].strip()
      
    logs_dir = os.path.abspath(os.path.join(base_dir, "..", "..", "..", "..", "logs", "agents", sim_code))
    os.makedirs(logs_dir, exist_ok=True)
    
    agent_log_path = os.path.join(logs_dir, f"{persona.name.replace(' ', '_')}.log")
    with open(agent_log_path, "a", encoding="utf-8") as f:
      f.write(f"=== 提示词模板：{prompt_template}\n")
      f.write("~~~ 智能体人物 (persona)   -------------------------------------------\n")
      f.write(f"{persona.name}\n\n")
      f.write("~~~ GPT 模型参数 (gpt_param) -----------------------------------------\n")
      f.write(f"{gpt_param}\n\n")
      f.write("~~~ 提示词输入参数 (prompt_input)   ----------------------------------\n")
      f.write(f"{prompt_input}\n\n")
      f.write("~~~ 最终拼装提示词 (prompt)   ----------------------------------------\n")
      f.write(f"{prompt}\n\n")
      f.write("~~~ 语言模型输出 (output)   ------------------------------------------\n")
      f.write(f"{output}\n\n")
      f.write("=== 结束 (END) ===================================================\n")
      f.write("\n\n\n")
  except Exception as e:
    print(f"Warning: Failed to write agent log: {e}")

