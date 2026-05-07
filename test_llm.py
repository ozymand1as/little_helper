import llm_integration
import sys

print("Sending request...")
res = llm_integration.process_user_input("add a task to feed the cat")
print("-" * 20)
print("FINAL RESULT:", res)
print("-" * 20)
