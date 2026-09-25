from core import Grok

response = Grok().start_convo("Hello, how are you today?")
print(response)

response2 = Grok().start_convo("That's nice! Glad to hear!", extra_data=response["extra_data"])
print(response2)