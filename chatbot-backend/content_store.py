# In-memory content store

content_data = {
    "tshirt": "Our t-shirts are 100% organic cotton, available in all sizes.",
    "sale": "20% off this week! Use code SALE20.",
    "contact": "Reach us at support@example.com or call +1234567890.",
    "shipping": "Free shipping on orders over $50. Delivery: 3-5 business days.",
}

def get_content_by_key(key: str):
    return content_data.get(key.lower())