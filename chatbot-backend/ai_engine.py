import logging
from content_store import get_content_by_key

logger = logging.getLogger(__name__)

def generate_reply(context: dict) -> str:
    """
    Central AI stub. In production: integrate LangChain/OpenAI here.
    """
    try:
        message = context.get("message", "").lower()
        qr_context = context.get("qr_context")
        language = context.get("language", "en")

        # Handle QR codes
        if qr_context:
            product_info = get_content_by_key(qr_context)
            if product_info:
                return f"Thanks for scanning QR for {qr_context}! {product_info}"
            return f"Thanks for scanning QR for {qr_context}! How can we help you today?"

        # Simple intents
        if "hello" in message or "hi" in message:
            return "Hello! How can I help you today?"
        if "help" in message:
            return "I can help with product info, order status, or support questions."
        if "bye" in message or "goodbye" in message:
            return "Thank you for chatting with us. Have a great day!"

        return "I'm here to help. Could you tell me more about what you need?"
    except Exception as e:
        logger.error(f"AI Engine error: {e}")
        return "I’m experiencing technical issues. Please try again later."