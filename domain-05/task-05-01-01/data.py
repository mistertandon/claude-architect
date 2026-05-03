def create_initial_case_facts() -> dict:
    return {
        "customer": {},
        "orders": [],
        "payments": [],
        "dates": {},
        "statuses": {},
    }


SIMULATED_CONVERSATION = [
    {
        "turn": 1,
        "user": (
            "Hi, I'm Jane Smith (jane.smith@example.com). I placed order "
            "#ORD-9821 on January 15th 2025 for a wireless keyboard — it was "
            "$149.99 but I haven't received it yet."
        ),
    },
    {
        "turn": 2,
        "user": (
            "I also made a payment of $149.99 via credit card on January 15th, "
            "payment reference PAY-4410. It shows as completed on my end."
        ),
    },
    {
        "turn": 3,
        "user": (
            "Actually I also have a second order #ORD-1087 from February 3rd "
            "for a USB-C hub, $39.99. That one arrived fine — I just need "
            "help with the keyboard order."
        ),
    },
    {
        "turn": 4,
        "user": (
            "Can you confirm exactly which orders I mentioned and their "
            "amounts? I want to make sure you have the right details before "
            "we proceed with a refund."
        ),
    },
]
