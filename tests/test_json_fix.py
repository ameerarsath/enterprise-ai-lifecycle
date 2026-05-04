from agents.model_wrapper import ModelWrapper

w = ModelWrapper()
text = '''```json
{"test": 123,}
```'''

print("Normalizer OK:", w._normalize_json(text))
