============================================================

### User: What's the weather in San Francisco?

============================================================

```
[stop_reason: tool_use]

  -> Calling tool: get_weather({"city": "San Francisco"})
  <- Result: {"temp_c": 15, "condition": "Foggy"}

[stop_reason: end_turn]
```

> Assistant: The current weather in **San Francisco** is **foggy** with a temperature of **15°C (59°F)**. Typical San Francisco weather — don't forget a jacket! 🌫️


============================================================

### User: Compare the weather in London and New York.

============================================================

```
[stop_reason: tool_use]

  -> Calling tool: get_weather({"city": "London"})
  <- Result: {"temp_c": 12, "condition": "Rainy"}
  -> Calling tool: get_weather({"city": "New York"})
  <- Result: {"temp_c": 22, "condition": "Sunny"}

[stop_reason: end_turn]
```

Assistant: Here's a comparison of the current weather in **London** and **New York**:

| | 🇬🇧 London | 🇺🇸 New York |
|---|---|---|
| **Temperature** | 12°C (53.6°F) | 22°C (71.6°F) |
| **Condition** | 🌧️ Rainy | ☀️ Sunny |

**Key Takeaways:**
- **New York** is significantly **warmer** than London by **10°C (18°F)**.
- **London** is experiencing **rainy** weather, while **New York** is enjoying **sunny** skies.

Overall, New York has much more pleasant weather at the moment compared to London!
