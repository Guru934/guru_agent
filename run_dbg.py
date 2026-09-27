import sys
from agent.policy import engine
engine.safe_mode = True
from tests.test_core_evals import CoreEvaluationSuite
suite = CoreEvaluationSuite("test_eval_07_executor_approvals_block_until_granted")
print("Running test 7...")
try:
    suite.setUp()
    suite.test_eval_07_executor_approvals_block_until_granted()
except Exception as e:
    print("FAILED:", e)
    import os
    os._exit(1)
