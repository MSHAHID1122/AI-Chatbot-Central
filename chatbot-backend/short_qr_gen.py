# CLI/utility that creates short links + QR images
from qr_utils import create_short_link, generate_qr_image, make_prefill, load_mapping, save_mapping, generate_session_token

if __name__ == "__main__":
    # Example product params
    phone = "14151234567"
    category = "tshirt"
    product_id = "TSHIRT-123"
    utm_medium = "hangtag"

    # create session token to match later inbound message
    session = generate_session_token()

    prefill = make_prefill(
        category=category,
        product_id=product_id,
        utm_source="qr",
        utm_medium=utm_medium,
        session=session
    )

    wa_long = f"https://wa.me/{phone}?text={quote_plus(prefill)}"

    short = create_short_link(wa_long)

    # Save mapping (demo local mapping contains the prefill + session token)
    mapping = load_mapping()
    short_id = short.rstrip("/").split("/")[-1]
    mapping[short_id] = {
        "phone": phone,
        "prefill": prefill,
        "session": session,
        "product_id": product_id,
        "category": category
    }
    save_mapping(mapping)

    print("Short link:", short)
    generate_qr_image(short, filename=f"{product_id}_qr.png")
    print("QR saved:", f"{product_id}_qr.png")