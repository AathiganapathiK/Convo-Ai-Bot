from semantic.semantic_gate import SemanticGate

tests = [
    {
        "name": "Complete",
        "semantic_result": {
            "retrieval": {
                "status": "COMPLETE",
                "confidence": 0.95,
                "resolved_components": 3
            }
        }
    },
    {
        "name": "Partial",
        "semantic_result": {
            "retrieval": {
                "status": "PARTIAL",
                "confidence": 0.55,
                "resolved_components": 1
            }
        }
    },
    {
        "name": "Insufficient",
        "semantic_result": {
            "retrieval": {
                "status": "INSUFFICIENT",
                "confidence": 0.0,
                "resolved_components": 0
            }
        }
    }
]

for test in tests:
    print("=" * 60)
    print(test["name"])
    print(SemanticGate.evaluate(test["semantic_result"]))