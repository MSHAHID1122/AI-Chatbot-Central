# ai_engine.py
from typing import List, Dict, Any, Optional
from pathlib import Path
import os
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.schema import Document
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_chroma import Chroma

from config import (
    OPENAI_API_KEY,
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    TOP_K,
    MAX_TOKENS
)

# Convert WindowsPath to string for ChromaDB compatibility
chroma_persist_dir_str = str(CHROMA_PERSIST_DIR)

# Initialize embeddings and vectorstore
embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
vectorstore = Chroma(
    persist_directory=chroma_persist_dir_str,
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
    """Load prompt template for the given language."""
    template_file = Path("prompts") / f"prompt_{lang}.txt"
    if not template_file.exists():
        template_file = Path("prompts") / "prompt_en.txt"
    
    template_content = template_file.read_text(encoding="utf-8")
    return PromptTemplate.from_template(template_content)

def _retrieve_docs(query: str, lang: str, k: int = TOP_K) -> List[Document]:
    """Retrieve relevant documents with optional language filtering."""
    try:
        if hasattr(vectorstore, "similarity_search"):
            try:
                return vectorstore.similarity_search(
                    query,
                    k=k,
                    filter={"language": lang}
                )
            except (TypeError, ValueError):
                return vectorstore.similarity_search(query, k=k)
    except Exception:
        return []
    
    return vectorstore.similarity_search(query, k=k)

def generate_reply(
    context: Dict[str, Any],
    language_detector: Optional[Any] = None,
    prompt_validator: Optional[Any] = None
) -> str:
    """
    Generate a reply using RAG with language-aware processing.
    """
    user_msg = context.get("message", "") or ""
    client_hint = context.get("language")

    # Detect language
    if language_detector and hasattr(language_detector, 'detect_language'):
        detect_result = language_detector.detect_language(user_msg, client_hint=client_hint)
        lang = detect_result.get("lang", "en")
    else:
        # Fallback language detection
        lang = client_hint if client_hint in ("en", "ar") else "en"
        if lang == "unknown":
            lang = "en"

    # Retrieve documents
    retrieved_docs = _retrieve_docs(user_msg, lang, k=TOP_K)
    snippets = "\n\n".join([doc.page_content for doc in retrieved_docs]) if retrieved_docs else ""

    # Conversation history
    conv_hist = context.get("conversation_history", [])
    conv_text = "\n".join([
        f"User: {h.get('user', '')}\nAssistant: {h.get('assistant', '')}"
        for h in conv_hist
    ]) if conv_hist else ""

    # Load prompt
    prompt_template = _load_prompt_template(lang)

    formatted_prompt = prompt_template.format(
        user_message=user_msg,
        retrieved_docs=snippets,
        conversation_history=conv_text,
        user_profile=context.get("user_profile", {}),
        product_context=context.get("product_context", {})
    )

    # Language guard
    language_guard = (
        "\n\nNow produce the assistant reply in Arabic only."
        if lang == "ar" else
        "\n\nNow produce the assistant reply in English only."
    )
    final_prompt = formatted_prompt + language_guard

    # Generate reply
    try:
        reply = llm.invoke(final_prompt).content
    except Exception as e:
        print(f"LLM prediction error: {e}")
        return "I'm experiencing technical difficulties. Please try again."

    # Enforce language
    if prompt_validator and hasattr(prompt_validator, 'enforce_output_language'):
        if not prompt_validator.enforce_output_language(reply, lang):
            stronger_prompt = final_prompt + (
                "\n\nIMPORTANT: RESPOND ONLY IN ARABIC."
                if lang == "ar" else
                "\n\nIMPORTANT: RESPOND ONLY IN ENGLISH."
            )
            try:
                reply2 = llm.invoke(stronger_prompt).content
                if prompt_validator.enforce_output_language(reply2, lang):
                    return reply2
            except Exception:
                pass

    return reply

def generate_replies(
    contexts: List[Dict[str, Any]],
    language_detector: Optional[Any] = None,
    prompt_validator: Optional[Any] = None
) -> List[str]:
    """Batch process multiple replies."""
    return [
        generate_reply(context, language_detector, prompt_validator)
        for context in contexts
    ]