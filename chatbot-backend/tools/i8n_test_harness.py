# tools/i18n_test_harness.py
import sys
import re
from app import i18n

TESTS = [
    ("T1", "مرحبا", "ar"),
    ("T2", "Hello there", "en"),
    ("T3", "OK", "unknown"),
    ("T4", "أريد استرجاع المنتج", "ar"),
    ("T5", "Order status #123456", "en"),
    ("T6", "شكراً لك!", "ar"),
    ("T7", "Hi, أحتاج مساعدة", "ar"),
    ("T8", "www.example.com/TSHIRT تفاصيل", "ar"),
    ("T9", "إيميل: user@example.com", "ar"),
    ("T10", "12345", "unknown"),
    ("T11", "ص.ب ١٢٣٤", "ar"),
    ("T12", "Is this available in M?", "en"),
    ("T13", "هل يوجد قياس M؟", "ar"),
    ("T14", "Thanks!", "en"),
    ("T15", "موافق. شكرا", "ar"),
    ("T16", "CAn you help?", "en"),
    ("T17", "السلام عليكم, Hi", "ar"),
    ("T18", "Special chars: ؟،؛", "ar"),
    ("T19", "Order #900: I need refund", "en"),
    ("T20", "اكتبوا لي التفاصيل", "ar"),
]

def run_tests():
    failures = []
    for tid, text, expected in TESTS:
        res = i18n.detect_language(text)
        detected = res.get("lang", "unknown")
        ok = (detected == expected) or (expected == "unknown" and detected == "unknown")
        print(f"{tid}: '{text[:40]}' -> detected={detected} expected={expected} conf={res.get('confidence'):.2f} method={res.get('method')}")
        if not ok:
            failures.append((tid, text, detected, expected))
    print(f"\nTotal: {len(TESTS)} Failures: {len(failures)}")
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(run_tests())