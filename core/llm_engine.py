# core/llm_engine.py
import json
from core.learning_table import load_learning_terms

def ask_llm(prompt: str, context: dict = None, model_name: str = "gemma:2b"):
    """
    Ask the local Gemma model via ollama (if available).
    Handles all errors safely. Automatically injects the learning table
    (shipping terminology) into the context when available.
    """

    # Build context text (short preview)
    ctx_text = ""
    try:
        if context:
            ctx_text = "\nCONTEXT:\n" + json.dumps(context, default=str)[:2000]
    except:
        ctx_text = ""

    # Load learning terms and add into context for LLM to reference
    learning_terms = {}
    try:
        learning_terms = load_learning_terms()
        if learning_terms:
            # include in the context dictionary (so other code can inspect it if needed)
            if context is None:
                context = {}
            context["shipping_terms"] = learning_terms
    except Exception:
        learning_terms = {}

    # Build a stronger system prompt that explicitly instructs the model to use the learning table
    system_prompt = "You are an expert data analyst. Use only the provided context and the shipping terminology table when answering."
    if learning_terms:
        # show a brief (not huge) excerpt of learning terms for the model
        brief_terms = ", ".join([f"{k}={v}" for k, v in list(learning_terms.items())[:20]])
        system_prompt += f"\n\nShipping terminology (examples): {brief_terms}\nIf a shipping term appears in the context or question, use the definition from the table."

    full_prompt = f"{ctx_text}\n\nQUESTION: {prompt}"

    # Try importing ollama
    try:
        import ollama
    except Exception as e:
        return (
            "LLM not available: Python 'ollama' client not installed.\n"
            "Install with: pip install ollama\n"
            f"Error: {e}"
        )

    # Call ollama WITHOUT timeout (older versions don't support it)
    try:
        # Use messages to pass system prompt + user content
        response = ollama.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ]
        )

        # Extract content safely (ollama API may return a dict or object)
        if isinstance(response, dict):
            msg = response.get("message", {})
            return msg.get("content", "No response content.")
        # Some ollama client versions return text directly
        return str(response)

    except Exception as e:
        return (
            f"LLM call failed: {e}\n"
            f"Make sure Ollama is running and model '{model_name}' is installed."
        )
