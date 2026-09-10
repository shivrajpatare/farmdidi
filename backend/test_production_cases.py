import sys
from backend.services.ai import parse_production_message

sys.stdout.reconfigure(encoding='utf-8')


def run_tests():
    test_suite = [
        {
            "name": "Case 1: User primary example with Hindi number word ('bees kilo')",
            "input": "Aaj aam ka achar banaungi, bees kilo.",
            "expected": {
                "production_status": "planned",
                "product": "Mango Achar",
                "quantity": 20.0,
                "unit": "kg",
            },
        },
        {
            "name": "Case 2: User primary example with digits ('20 kilo')",
            "input": "Aaj aam ka achar 20 kilo banaungi",
            "expected": {
                "production_status": "planned",
                "product": "Mango Achar",
                "quantity": 20.0,
                "unit": "kg",
            },
        },
        {
            "name": "Case 3: Lemon Achar with Hindi number word ('pandrah kg')",
            "input": "Nimbu ka achar pandrah kg banayenge",
            "expected": {
                "production_status": "planned",
                "product": "Lemon Achar",
                "quantity": 15.0,
                "unit": "kg",
            },
        },
        {
            "name": "Case 4: Chilli Achar with Hindi word ('das kilo')",
            "input": "Mirchi ka achar das kilo",
            "expected": {
                "production_status": "planned",
                "product": "Chilli Achar",
                "quantity": 10.0,
                "unit": "kg",
            },
        },
        {
            "name": "Case 5: Garlic Achar ('5 kilo')",
            "input": "Lahsun ka achar 5 kilo banaungi",
            "expected": {
                "production_status": "planned",
                "product": "Garlic Achar",
                "quantity": 5.0,
                "unit": "kg",
            },
        },
        {
            "name": "Case 6: Explicit No Production ('koi production nahi')",
            "input": "Aaj koi production nahi hoga, tabiyat kharab hai",
            "expected": {
                "production_status": "none",
                "product": None,
                "quantity": None,
                "unit": None,
            },
        },
        {
            "name": "Case 7: Explicit No Production ('kuch nahi bana rahi')",
            "input": "Aaj kuch nahi bana rahi hoon",
            "expected": {
                "production_status": "none",
                "product": None,
                "quantity": None,
                "unit": None,
            },
        },
        {
            "name": "Case 8: Ambiguous / Unresolved Quantity Range ('20 ya 30 kilo')",
            "input": "Aaj aam ka achar banaungi, 20 ya 30 kilo",
            "expected": {
                "production_status": "planned",
                "product": "Mango Achar",
                "quantity": None,
                "unit": None,
            },
        },
    ]

    passed = 0
    failed = 0
    results = []

    print("=" * 60)
    print("PHASE 5 - STEP 2: PRODUCTION MESSAGE UNDERSTANDING TEST SUITE")
    print("=" * 60)

    for case in test_suite:
        text = case["input"]
        exp = case["expected"]
        print(f"\nRunning: {case['name']}")
        print(f"Input:    \"{text}\"")

        try:
            update = parse_production_message(text)
            actual = {
                "production_status": update.production_status,
                "product": update.product,
                "quantity": update.quantity,
                "unit": update.unit,
            }
            print(f"Extracted: {actual}")

            # Check assertions
            assert actual["production_status"] == exp["production_status"], (
                f"production_status mismatch: expected {exp['production_status']}, got {actual['production_status']}"
            )
            assert actual["product"] == exp["product"], (
                f"product mismatch: expected {exp['product']}, got {actual['product']}"
            )
            assert actual["quantity"] == exp["quantity"], (
                f"quantity mismatch: expected {exp['quantity']}, got {actual['quantity']}"
            )
            assert actual["unit"] == exp["unit"], (
                f"unit mismatch: expected {exp['unit']}, got {actual['unit']}"
            )

            print("Result:   [PASS]")
            passed += 1
            results.append({"case": case["name"], "status": "PASS", "output": actual})
        except Exception as e:
            print(f"Result:   [FAIL] - {e}")
            failed += 1
            results.append({"case": case["name"], "status": "FAIL", "error": str(e)})

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed} PASSED, {failed} FAILED (Total: {len(test_suite)})")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
