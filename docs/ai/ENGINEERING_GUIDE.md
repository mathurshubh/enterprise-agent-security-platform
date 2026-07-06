# Engineering Guide

Never redesign the architecture unless explicitly requested.

Always preserve deterministic security decisions.

Never move authorization into the LLM.

The LLM is only responsible for producing ToolInvocation objects.

Authorization, Detection, Risk, Response and Audit remain deterministic.

Prefer dependency injection.

Prefer Protocols over concrete implementations.

Prefer incremental pull requests.

Do not modify unrelated files.

Maintain backward compatibility.

Always add tests.

Run:

pytest

before considering work complete.