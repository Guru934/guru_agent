import sys
import logging
from cat_talker.heavy_agent import run_heavy_agent_worker

# Hook the logger to stdout
run_heavy_agent_worker("Run `echo 'hello from heavy agent'` using your shell tool.")
