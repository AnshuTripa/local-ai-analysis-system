# core/llm_engine.py  (FULLY UPDATED)
# Compatible with Ollama Python SDK & offline LLMs (gemma, llama3.2, mistral, etc.)

import json
import ollama


def ask_llm(question: str, context: dict = None, model_name: str = "gemma:2b") -> str:
    """
    Run an offline LLM query using Ollama with context-awareness.

    Automatically builds:
    - System context
    - User question
    - Handles offline model errors safely
    - Returns plain text response only
    """

    # Convert context into readable JSON text
    messages = []

    if context:
        try:
            ctx_text = json.dumps(context, indent=2)
        except:
            ctx_text = str(context)

        messages.append({
            "role": "system",
            "content": "Use ONLY the following structured context:\n" + ctx_text
        })

    # User question
    messages.append({"role": "user", "content": question})

    try:
        # NEW correct Ollama API call
        response = ollama.chat(
            model=model_name,
            messages=messages
        )

        # Extract only the assistant message
        return response.get("message", {}).get("content", "")

    except Exception as e:
        # Very clean & readable error message
        return (
            "LLM Error: " + str(e)
            + "\nPossible Causes:\n"
            + "- Ollama model not installed (try: ollama pull gemma:2b)\n"
            + "- Ollama server not running (run: ollama serve)\n"
            + "- Model name is incorrect\n"
        )
