from app.services.agent_runtime_service import (
    AgentRuntimeService,
)

service = AgentRuntimeService()

while True:
    query = input("\nQuery (or 'quit'): ")

    if query.lower() in {"quit", "exit"}:
        break

    result = service.execute(query)

    print("\nResult:")
    print(result)