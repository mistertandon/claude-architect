############################################################
# The model will likely say 'Let me check...' AND call a tool.
# The text-presence check fires on the text → tool call is dropped.
############################################################

============================================================
ANTI-PATTERN: Text presence as completion signal
============================================================
User: Check my balance on ACC-001, show recent transactions, then transfer $100 to ACC-002.


Model response Message(id='msg_01Q5Snu1W9CwediFqsfXPKbk', container=None, content=[TextBlock(citations=None, text="Sure! I'll start by checking your balance and fetching your recent transactions for ACC-001 simultaneously right away!\n\n**Step 1: Get balance & transactions in parallel...**", type='text'), ToolUseBlock(id='toolu_018pn8d1W3C3bWD5jgAHZNLq', caller=DirectCaller(type='direct'), input={'account_id': 'ACC-001'}, name='get_account_balance', type='tool_use'), ToolUseBlock(id='toolu_01J2Lcxjekn65Qe9reXbHpdZ', caller=DirectCaller(type='direct'), input={'account_id': 'ACC-001'}, name='get_transactions', type='tool_use')], model='claude-sonnet-4-6', role='assistant', stop_details=None, stop_reason='tool_use', stop_sequence=None, type='message', usage=Usage(cache_creation=CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0), cache_creation_input_tokens=0, cache_read_input_tokens=0, inference_geo='global', input_tokens=791, output_tokens=138, server_tool_use=None, service_tier='standard'))
  [Iteration 1 | stop_reason: tool_use]
  Content blocks: ['text', 'tool_use', 'tool_use']
  >>> Text detected — assuming completion <<<

Assistant: Sure! I'll start by checking your balance and fetching your recent transactions for ACC-001 simultaneously right away!

**Step 1: Get balance & transactions in parallel...**

  !!! DROPPED TOOL CALLS: ['get_account_balance', 'get_transactions'] !!!
  Total iterations: 1
