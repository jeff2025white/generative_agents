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
