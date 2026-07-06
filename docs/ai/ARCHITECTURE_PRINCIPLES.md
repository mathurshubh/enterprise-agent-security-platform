# Runtime

RuntimeService is the single deterministic security pipeline.

AgentRuntimeService is only responsible for:

- LLM invocation
- ToolInvocation generation
- Executing approved tools

Never duplicate runtime orchestration.

---

# Trust Boundary

User

↓

LLM (untrusted)

↓

ToolInvocation

↓

RuntimeService

↓

Authorization

↓

Detection

↓

Risk

↓

Response

↓

Tool Execution