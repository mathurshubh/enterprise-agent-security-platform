import assert from 'node:assert/strict'
import { after, before, describe, test } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

describe('ScenarioTimeline Component & Evidence Contract', () => {
  let viteServer
  let ScenarioTimeline

  before(async () => {
    viteServer = await createServer({
      server: { middlewareMode: true },
      appType: 'custom',
    })
    const mod = await viteServer.ssrLoadModule(
      './src/pages/Scenarios/components/ScenarioTimeline.tsx'
    )
    ScenarioTimeline = mod.default
  })

  after(async () => {
    if (viteServer) {
      await viteServer.close()
    }
  })

  test('Normal prompt scenario: renders all 8 causal stages, LLM trust boundary, and canonical checks', () => {
    const evidence = {
      request: {
        agentId: 'test-agent',
        executionMode: 'PROMPT',
        userPrompt: 'Please read customer_records.csv',
        intentSource: 'UNTRUSTED_LLM_PARSER',
        toolSequence: [],
        toolInvocation: {
          toolId: 'file_read',
          resource: 'customer_records.csv',
        },
      },
      authorization: {
        decision: 'ALLOW',
        reason: 'All authorization controls passed',
        checks: [
          {
            name: 'Agent existence',
            key: 'agent_check',
            status: 'passed',
            reason: 'Agent verified',
            details: { agent_id: 'test-agent' },
          },
          {
            name: 'Tool existence',
            key: 'tool_check',
            status: 'passed',
            reason: 'Tool registered',
            details: { tool_id: 'file_read' },
          },
          {
            name: 'Approved tool (RBAC)',
            key: 'approved_tool_check',
            status: 'passed',
            reason: 'Tool approved for agent',
            details: { tool_id: 'file_read' },
          },
          {
            name: 'Agent status',
            key: 'status_check',
            status: 'passed',
            reason: 'Agent is active',
            details: { status: 'ACTIVE' },
          },
          {
            name: 'Risk tier alignment',
            key: 'risk_tier_check',
            status: 'passed',
            reason: 'Tool tier matches agent allowance',
            details: { risk_tier: 'READ_ONLY' },
          },
          {
            name: 'Resource policy',
            key: 'resource_check',
            status: 'passed',
            reason: 'Resource allowed',
            details: { resource: 'customer_records.csv' },
          },
        ],
      },
      detection: {
        findingCount: 1,
        findings: [
          {
            ruleName: 'SENSITIVE_FILE_ACCESS',
            severity: 'MEDIUM',
            findingId: 'find-101',
            description: 'Access to customer data file detected',
          },
        ],
      },
      risk: {
        level: 'MEDIUM',
        score: 45,
        findingCount: 1,
      },
      response: {
        action: 'ALERT',
        reason: 'Medium risk policy dictates alert notification',
      },
      audit: {
        eventId: 'evt-audit-12345',
      },
      finalDecision: {
        decision: 'ALLOW',
      },
      refusalReason: null,
    }

    const html = renderToStaticMarkup(React.createElement(ScenarioTimeline, { evidence }))

    // Stage 1: Request
    assert.ok(html.includes('Request'), 'Stage 1 Request must be rendered')
    assert.ok(html.includes('test-agent'), 'Agent ID must be present')
    assert.ok(html.includes('Please read customer_records.csv'), 'User prompt must be present')

    // Stage 2: Intent & LLM Trust Boundary
    assert.ok(html.includes('Intent'), 'Stage 2 Intent must be rendered')
    assert.ok(html.includes('Untrusted Intent Parser (LLM)'), 'LLM untrusted parser badge must be present')
    assert.ok(html.includes('LLM Trust Boundary:'), 'LLM trust boundary warning must be present')
    assert.ok(html.includes('file_read'), 'Target tool must be present')
    assert.ok(html.includes('customer_records.csv'), 'Resource target must be present')

    // Stage 3: Authorization & 6 Canonical Checks
    assert.ok(html.includes('Authorization'), 'Stage 3 Authorization must be rendered')
    assert.ok(html.includes('All authorization controls passed'), 'Policy reason must be present')
    assert.ok(html.includes('agent_check'), 'agent_check must be present')
    assert.ok(html.includes('tool_check'), 'tool_check must be present')
    assert.ok(html.includes('approved_tool_check'), 'approved_tool_check must be present')
    assert.ok(html.includes('status_check'), 'status_check must be present')
    assert.ok(html.includes('risk_tier_check'), 'risk_tier_check must be present')
    assert.ok(html.includes('resource_check'), 'resource_check must be present')

    // Stage 4: Detection
    assert.ok(html.includes('Detection'), 'Stage 4 Detection must be rendered')
    assert.ok(html.includes('SENSITIVE_FILE_ACCESS'), 'Rule name must be present')
    assert.ok(html.includes('find-101'), 'Finding ID must be present')

    // Stage 5: Risk
    assert.ok(html.includes('Risk'), 'Stage 5 Risk must be rendered')
    assert.ok(html.includes('MEDIUM'), 'Risk level must be present')
    assert.ok(html.includes('45'), 'Risk score must be present')

    // Stage 6: Response
    assert.ok(html.includes('Response'), 'Stage 6 Response must be rendered')
    assert.ok(html.includes('ALERT'), 'Recommended action must be present')
    assert.ok(html.includes('Medium risk policy dictates alert notification'), 'Response reason must be present')

    // Stage 7: Audit
    assert.ok(html.includes('Audit'), 'Stage 7 Audit must be rendered')
    assert.ok(html.includes('evt-audit-12345'), 'Correlated audit event ID must be present')

    // Stage 8: Final Decision
    assert.ok(html.includes('Final Decision'), 'Stage 8 Final Decision must be rendered')
    assert.ok(html.includes('ALLOW'), 'Final decision must be present')
  })

  test('Normal tool sequence scenario: renders deterministic sequence intent', () => {
    const evidence = {
      request: {
        agentId: 'batch-agent',
        executionMode: 'TOOL_SEQUENCE',
        userPrompt: null,
        intentSource: 'DETERMINISTIC_SEQUENCE',
        toolSequence: ['dir_list', 'file_read'],
        toolInvocation: {
          toolId: 'dir_list',
          resource: null,
        },
      },
      authorization: {
        decision: 'ALLOW',
        reason: 'Authorized',
        checks: [
          {
            name: 'Agent existence',
            key: 'agent_check',
            status: 'passed',
            reason: 'Agent verified',
            details: {},
          },
        ],
      },
      detection: { findingCount: 0, findings: [] },
      risk: { level: 'LOW', score: 0, findingCount: 0 },
      response: { action: 'MONITOR', reason: 'LOW risk' },
      audit: { eventId: 'evt-seq-99' },
      finalDecision: { decision: 'ALLOW' },
      refusalReason: null,
    }

    const html = renderToStaticMarkup(React.createElement(ScenarioTimeline, { evidence }))

    assert.ok(html.includes('Deterministic Sequence (Zero-LLM)'), 'Deterministic badge must be present')
    assert.ok(html.includes('Deterministic Intent:'), 'Deterministic explanation must be present')
    assert.ok(html.includes('dir_list'), 'Tool in sequence must be present')
    assert.ok(!html.includes('Untrusted Intent Parser (LLM)'), 'Must not display LLM parser for sequence mode')
  })

  test('Refusal scenario: renders trust boundary refusal and unreached downstream stages without synthetic decisions', () => {
    const evidence = {
      request: {
        agentId: 'rogue-agent',
        executionMode: 'TOOL_SEQUENCE',
        userPrompt: null,
        intentSource: 'DETERMINISTIC_SEQUENCE',
        toolSequence: ['file_read'],
        toolInvocation: {
          toolId: 'file_read',
          resource: null,
        },
      },
      authorization: null,
      detection: null,
      risk: null,
      response: null,
      audit: {
        eventId: 'evt-refusal-777',
      },
      finalDecision: {
        decision: 'DENY',
      },
      refusalReason: 'SESSION_BINDING_INVALID',
    }

    const html = renderToStaticMarkup(React.createElement(ScenarioTimeline, { evidence }))

    // Refusal banner
    assert.ok(html.includes('Trust Boundary Refusal'), 'Refusal banner must be present')
    assert.ok(html.includes('SESSION_BINDING_INVALID'), 'Refusal reason must be present')

    // Unreached stages
    assert.ok(html.includes('UNREACHED'), 'Unreached badge must be present')
    assert.ok(html.includes('Skipped due to trust boundary refusal (SESSION_BINDING_INVALID)'), 'Explanation must cite refusal')

    // Audit and Final decision are present as recorded
    assert.ok(html.includes('evt-refusal-777'), 'Audit event ID must be present')
    assert.ok(html.includes('DENY'), 'Actual final decision must be rendered')

    // Must NOT manufacture authorization decision
    assert.ok(!html.includes('Policy Outcome:'), 'Must not fabricate policy outcome when authorization is null')
  })

  test('Decision divergence: renders independent authorization and final decisions with factual variance note', () => {
    const evidence = {
      request: {
        agentId: 'compromised-agent',
        executionMode: 'TOOL_SEQUENCE',
        userPrompt: null,
        intentSource: 'DETERMINISTIC_SEQUENCE',
        toolSequence: ['file_write'],
        toolInvocation: { toolId: 'file_write', resource: '/etc/hosts' },
      },
      authorization: {
        decision: 'ALLOW',
        reason: 'Static authorization policy permitted action',
        checks: [
          {
            name: 'Agent existence',
            key: 'agent_check',
            status: 'passed',
            reason: 'Agent verified',
            details: {},
          },
        ],
      },
      detection: {
        findingCount: 1,
        findings: [
          {
            ruleName: 'SYSTEM_FILE_TAMPERING',
            severity: 'CRITICAL',
            findingId: 'find-999',
            description: 'Attempted modification of system hosts file',
          },
        ],
      },
      risk: { level: 'CRITICAL', score: 95, findingCount: 1 },
      response: {
        action: 'SUSPEND_AGENT',
        reason: 'Critical severity finding requires immediate suspension',
      },
      audit: { eventId: 'evt-div-888' },
      finalDecision: { decision: 'DENY' },
      refusalReason: null,
    }

    const html = renderToStaticMarkup(React.createElement(ScenarioTimeline, { evidence }))

    // Both decisions present independently
    assert.ok(html.includes('ALLOW'), 'Initial authorization ALLOW must be present')
    assert.ok(html.includes('DENY'), 'Final decision DENY must be present')

    // Factual variance note
    assert.ok(html.includes('Decision Variance:'), 'Decision variance banner must be present')
    assert.ok(
      html.includes('Initial authorization was') && html.includes('final pipeline outcome is'),
      'Must explain factual difference between authorization and final decision'
    )

    // Invariant: Must NOT synthesize "Enforcement Override" or "Overridden by Response Engine"
    assert.ok(!html.includes('Enforcement Override'), 'Must not invent an Enforcement Override semantic')
    assert.ok(!html.includes('Overridden by Response Engine'), 'Must not synthesize Response Engine override')
  })

  test('Untrusted user prompt escaping: strictly escapes potential HTML/script payloads', () => {
    const evidence = {
      request: {
        agentId: 'attacker',
        executionMode: 'PROMPT',
        userPrompt: '<script>alert("xss")</script><img src=x onerror=alert(1)>',
        intentSource: 'UNTRUSTED_LLM_PARSER',
        toolSequence: [],
        toolInvocation: null,
      },
      authorization: null,
      detection: null,
      risk: null,
      response: null,
      audit: null,
      finalDecision: null,
      refusalReason: 'MALFORMED_INPUT',
    }

    const html = renderToStaticMarkup(React.createElement(ScenarioTimeline, { evidence }))

    // Must be properly escaped in output HTML
    assert.ok(!html.includes('<script>alert("xss")</script>'), 'Unescaped script tags must not be in HTML')
    assert.ok(html.includes('&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;') || html.includes('&lt;script&gt;alert'), 'Prompt must be safely HTML entity escaped')
  })

  test('Authorization check states: distinguishes PASSED, FAILED, and NOT EVALUATED', () => {
    const evidence = {
      request: {
        agentId: 'test-agent',
        executionMode: 'TOOL_SEQUENCE',
        intentSource: 'DETERMINISTIC_SEQUENCE',
      },
      authorization: {
        decision: 'DENY',
        reason: 'Tool check failed',
        checks: [
          {
            name: 'Agent existence',
            key: 'agent_check',
            status: 'passed',
            reason: 'Agent verified',
            details: {},
          },
          {
            name: 'Tool existence',
            key: 'tool_check',
            status: 'failed',
            reason: 'Tool not found',
            details: { tool_id: 'unknown_tool' },
          },
          {
            name: 'Approved tool (RBAC)',
            key: 'approved_tool_check',
            status: 'not_evaluated',
            reason: 'Skipped due to prior check failure',
            details: { skipped_after: 'tool_check' },
          },
        ],
      },
      detection: { findingCount: 0, findings: [] },
      risk: { level: 'LOW', score: 0, findingCount: 0 },
      response: { action: 'MONITOR', reason: 'LOW risk' },
      audit: { eventId: 'evt-chk-1' },
      finalDecision: { decision: 'DENY' },
      refusalReason: null,
    }

    const html = renderToStaticMarkup(React.createElement(ScenarioTimeline, { evidence }))

    assert.ok(html.includes('PASSED'), 'PASSED badge must be present')
    assert.ok(html.includes('FAILED'), 'FAILED badge must be present')
    assert.ok(html.includes('NOT EVALUATED'), 'NOT EVALUATED badge must be present')
    assert.ok(html.includes('skipped_after:</span> tool_check'), 'Details must be rendered')
  })
})
