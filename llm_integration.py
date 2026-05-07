import os
import litellm

# Provide llama.cpp server configuration via env vars
LLAMA_CPP_URL = os.environ.get("LLAMA_CPP_URL", "http://localhost:8080/v1")
LLAMA_CPP_API_KEY = os.environ.get("LLAMA_CPP_API_KEY", "sk-no-key-required")

def summarize_task(text: str) -> str:
    """
    Uses the local LLM to turn a raw user input into a clean, short task description.
    """
    system_prompt = (
        "You are a helpful assistant that cleans up task descriptions. "
        "The user will provide a raw request. Extract the main action into a short (3-7 words) imperative sentence. "
        "Do NOT include dates or conversational filler. "
        "Example: 'Remind me to buy some milk today' -> 'Buy milk'. "
        "Example: 'I need to finish the quarterly report by Friday' -> 'Finish quarterly report'."
    )
    
    try:
        response = litellm.completion(
            model="openai/local-model",
            api_base=LLAMA_CPP_URL,
            api_key=LLAMA_CPP_API_KEY,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.1,
            max_tokens=50
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Fallback to the original text if LLM fails
        print(f"LLM Summary Error: {e}")
        return text
