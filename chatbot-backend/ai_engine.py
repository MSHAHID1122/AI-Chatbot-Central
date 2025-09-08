# ai_engine.py
from typing import List, Dict, Any
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from pathlib import Path

from config import (
    OPENAI_API_KEY,
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    TOP_K,
    MAX_TOKENS
)

from app import i18n, prompt_manager

# Initialize embeddings and vectorstore
embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
vectorstore = Chroma(
    persist_directory=CHROMA_PERSIST_DIR,
    collection_name=CHROMA_COLLECTION_NAME,
    embedding_function=embeddings
)

# Initialize LLM
llm = ChatOpenAI(
    openai_api_key=OPENAI_API_KEY,
    model_name="gpt-3.5-turbo",
    temperature=0.3,
    max_tokens=MAX_TOKENS
)

def _load_prompt_template(lang: str) -> PromptTemplate:
    """Load prompt template for the given language using LangChain's PromptTemplate."""
    template_file = Path("prompts") / f"prompt_{lang}.txt"
    if not template_file.exists():
        # Fallback to English if language-specific template doesn't exist
        template_file = Path("prompts") / "prompt_en.txt"
    
    template_content = template_file.read_text(encoding="utf-8")
    return PromptTemplate.from_template(template_content)

def _retrieve_docs(query: str, lang: str, k: int = TOP_K) -> List[Document]:
    """
    Retrieve documents with language filtering if supported by the vectorstore.
    Falls back to simple similarity search if language filtering is not available.
    """
    try:
        # Try language-filtered search if the vectorstore supports it
        if hasattr(vectorstore, "similarity_search"):
            try:
                # Attempt metadata-based language filtering
                docs = vectorstore.similarity_search(
                    query, 
                    k=k, 
                    filter={"language": lang}  # Updated to use 'filter' parameter
                )
                return docs
            except (TypeError, ValueError):
                # Fallback: vectorstore doesn't support filtering or language metadata
                return vectorstore.similarity_search(query, k=k)
            except Exception:
                # Any other error - fall back to simple search
                return vectorstore.similarity_search(query, k=k)
    except Exception:
        # Final fallback: return empty list if anything goes wrong
        return []
    
    return vectorstore.similarity_search(query, k=k)

def generate_reply(context: Dict[str, Any]) -> str:
    """
    Generate a reply using RAG with language-aware processing.
    
    Context should include:
    - message: user's input text
    - language: optional client language hint
    - conversation_history: list of previous messages
    - user_profile: user information
    - product_context: product-related context
    
    Returns: generated reply string
    """
    user_msg = context.get("message", "") or ""
    client_hint = context.get("language")
    
    # Detect language with client hint support
    detect_result = i18n.detect_language(user_msg, client_hint=client_hint)
    lang = detect_result.get("lang", "en")
    if lang == "unknown":
        lang = client_hint if client_hint in ("en", "ar") else "en"

    # Retrieve language-filtered documents
    retrieved_docs = _retrieve_docs(user_msg, lang, k=TOP_K)
    snippets = "\n\n".join([doc.page_content for doc in retrieved_docs]) if retrieved_docs else ""

    # Prepare conversation history
    conv_hist = context.get("conversation_history", [])
    conv_text = "\n".join([
        f"User: {h.get('user', '')}\nAssistant: {h.get('assistant', '')}" 
        for h in conv_hist
    ]) if conv_hist else ""

    # Load appropriate prompt template
    prompt_template = _load_prompt_template(lang)
    
    # Format the prompt with all context variables
    formatted_prompt = prompt_template.format(
        user_message=user_msg,
        retrieved_docs=snippets,
        conversation_history=conv_text,
        user_profile=context.get("user_profile", {}),
        product_context=context.get("product_context", {})
    )

    # Add language enforcement instruction
    language_guard = (
        "\n\nNow produce the assistant reply in Arabic only." 
        if lang == "ar" else 
        "\n\nNow produce the assistant reply in English only."
    )
    final_prompt = formatted_prompt + language_guard

    # Generate initial reply
    try:
        reply = llm.predict(final_prompt)
    except Exception as e:
        # Log the error and provide a fallback response
        print(f"LLM prediction error: {e}")
        return "I apologize, but I'm experiencing technical difficulties. Please try again."

    # Post-generation language validation with retry
    if not prompt_manager.enforce_output_language(reply, lang):
        # Attempt retry with stronger language enforcement
        stronger_prompt = final_prompt + (
            "\n\nIMPORTANT: RESPOND ONLY IN ARABIC. DO NOT USE ENGLISH." 
            if lang == "ar" else 
            "\n\nIMPORTANT: RESPOND ONLY IN ENGLISH. DO NOT USE ARABIC."
        )
        try:
            reply2 = llm.predict(stronger_prompt)
            if prompt_manager.enforce_output_language(reply2, lang):
                return reply2
        except Exception:
            # If retry fails, return original reply with potential language issue
            pass

    return reply

# Optional: Helper function for batch processing or testing
def generate_replies(contexts: List[Dict[str, Any]]) -> List[str]:
    """Generate multiple replies for batch processing."""
    return [generate_reply(context) for context in contexts]