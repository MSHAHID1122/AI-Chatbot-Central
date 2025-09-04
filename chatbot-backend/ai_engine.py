from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_chroma import Chroma
from langchain.schema import Document

# Import configs from centralized config.py
from config import OPENAI_API_KEY, CHROMA_PERSIST_DIR, TOP_K, MAX_TOKENS

# Load Chroma DB
vectorstore = Chroma(
    persist_directory=CHROMA_PERSIST_DIR,
    embedding_function=None  # assumes embedding_function is already persisted
)

# Load prompts
PROMPT_TEMPLATES = {
    "en": PromptTemplate.from_file("prompts/prompt_en.txt", encoding="utf-8"),
    "ar": PromptTemplate.from_file("prompts/prompt_ar.txt", encoding="utf-8")
}

# Chat model
llm = ChatOpenAI(
    openai_api_key=OPENAI_API_KEY,
    model_name="gpt-3.5-turbo",
    temperature=0.3,
    max_tokens=MAX_TOKENS
)

def generate_reply(context: dict) -> str:
    """
    RAG generation:
    - context: {user_id, message, qr_context, language, conversation_history=[]}
    - Returns localized reply using retrieved docs
    """
    user_msg = context.get("message", "")
    lang = context.get("language", "en")
    conversation_history = context.get("conversation_history", [])

    # Retrieve top-k relevant docs
    retrieved_docs: list[Document] = vectorstore.similarity_search(user_msg, k=TOP_K)
    snippets = "\n".join([doc.page_content for doc in retrieved_docs])

    # Build prompt
    prompt = PROMPT_TEMPLATES.get(lang, PROMPT_TEMPLATES["en"]).format(
        user_message=user_msg,
        retrieved_docs=snippets
    )

    # Optionally append conversation history for sliding window context
    if conversation_history:
        history_text = "\n".join(
            [f"User: {h['user']}\nAssistant: {h['assistant']}" for h in conversation_history]
        )
        prompt = history_text + "\n" + prompt

    # Generate reply
    response = llm.predict(prompt)
    return response