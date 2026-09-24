import type {
  ScenarioAuthorizationCheck,
  ScenarioExecutionEvidence,
} from '../../../types/scenario'

interface ScenarioTimelineProps {
  evidence: ScenarioExecutionEvidence
}

const CHECK_KEY_LABELS: Record<string, string> = {
  agent_check: 'Agent existence',
  tool_check: 'Tool existence',
  approved_tool_check: 'Approved tool (RBAC)',
  status_check: 'Agent status',
  risk_tier_check: 'Risk tier alignment',
  resource_check: 'Resource policy',
}

const DECISION_BADGES: Record<string, string> = {
  ALLOW: 'bg-status-active/15 text-status-active border-status-active/30',
  DENY: 'bg-status-error/15 text-status-error border-status-error/30',
  APPROVAL_REQUIRED: 'bg-status-warning/15 text-status-warning border-status-warning/30',
}

const RISK_BADGES: Record<string, string> = {
  LOW: 'bg-status-active/15 text-status-active border-status-active/30',
  MEDIUM: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  HIGH: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
  CRITICAL: 'bg-status-error/20 text-status-error border-status-error/40 font-bold',
}

const RESPONSE_BADGES: Record<string, string> = {
  MONITOR: 'bg-status-info/15 text-status-info border-status-info/30',
  ALERT: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  REQUIRE_APPROVAL: 'bg-status-warning/15 text-status-warning border-status-warning/30 font-semibold',
  SUSPEND_AGENT: 'bg-status-error/15 text-status-error border-status-error/30 font-bold',
}

const CHECK_STATUS_BADGES: Record<string, { label: string; badge: string }> = {
  passed: {
    label: 'PASSED',
    badge: 'bg-status-active/15 text-status-active border-status-active/30',
  },
  failed: {
    label: 'FAILED',
    badge: 'bg-status-error/15 text-status-error border-status-error/30 font-semibold',
  },
  not_evaluated: {
    label: 'NOT EVALUATED',
    badge: 'bg-status-warning/15 text-status-warning border-status-warning/30',
  },
}

function StageHeader({
  stepNumber,
  title,
  isUnreached = false,
  badgeText,
  badgeClass,
}: {
  stepNumber: number
  title: string
  isUnreached?: boolean
  badgeText?: string
  badgeClass?: string
}) {
  return (
    <div className="flex items-center justify-between pb-2 border-b border-border-secondary">
      <div className="flex items-center gap-2">
        <span
          className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
            isUnreached
              ? 'bg-bg-secondary text-text-muted border border-border-secondary'
              : 'bg-accent-primary/20 text-accent-primary border border-accent-primary/40'
          }`}
        >
          {stepNumber}
        </span>
        <span className={`text-xs font-bold uppercase tracking-wider ${isUnreached ? 'text-text-muted' : 'text-text-primary'}`}>
          {title}
        </span>
      </div>
      {badgeText && (
        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${badgeClass || 'bg-bg-secondary text-text-muted border-border-secondary'}`}>
          {badgeText}
        </span>
      )}
    </div>
  )
}

function UnreachedStage({
  stepNumber,
  title,
  reason = 'Stage was not reached by the execution pipeline.',
}: {
  stepNumber: number
  title: string
  reason?: string
}) {
  return (
    <div className="p-3.5 rounded-xl bg-bg-surface/50 border border-border-secondary/60 space-y-2 opacity-65">
      <StageHeader
        stepNumber={stepNumber}
        title={title}
        isUnreached
        badgeText="UNREACHED"
        badgeClass="bg-bg-secondary text-text-muted border-border-secondary"
      />
      <p className="text-[11px] text-text-muted italic">{reason}</p>
    </div>
  )
}

export default function ScenarioTimeline({ evidence }: ScenarioTimelineProps) {
  const req = evidence.request
  const auth = evidence.authorization
  const det = evidence.detection
  const risk = evidence.risk
  const resp = evidence.response
  const audit = evidence.audit
  const finalDec = evidence.finalDecision
  const refusal = evidence.refusalReason

  const decisionsDiffer =
    auth && finalDec && auth.decision !== finalDec.decision

  return (
    <div className="space-y-4 pt-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold uppercase tracking-wider text-text-muted">
          Authoritative Execution Timeline
        </h4>
        <span className="text-[10px] text-text-muted font-mono">
          8 Causal Pipeline Stages
        </span>
      </div>

      {/* ── Refusal Banner (if applicable) ─────────────────────────── */}
      {refusal && (
        <div className="p-3.5 rounded-xl bg-status-error/10 border border-status-error/30 space-y-1">
          <div className="flex items-center gap-2 text-status-error font-bold text-xs uppercase tracking-wider">
            <span>Trust Boundary Refusal</span>
          </div>
          <p className="text-xs text-text-secondary">
            Pipeline halted before evaluation: <span className="font-mono font-semibold text-status-error">{refusal}</span>.
            Downstream stages were skipped.
          </p>
        </div>
      )}

      {/* ── STAGE 1: REQUEST ────────────────────────────────────────── */}
      <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
        <StageHeader
          stepNumber={1}
          title="Request"
          badgeText={req.executionMode}
          badgeClass="bg-accent-primary/10 text-accent-primary border-accent-primary/30"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px]">
          <div>
            <span className="text-text-muted text-[10px] uppercase font-semibold">Agent ID</span>
            <div className="font-mono text-text-primary mt-0.5">{req.agentId}</div>
          </div>
          <div>
            <span className="text-text-muted text-[10px] uppercase font-semibold">Execution Mode</span>
            <div className="font-mono text-text-primary mt-0.5">{req.executionMode}</div>
          </div>
        </div>

        {req.userPrompt && (
          <div className="space-y-1">
            <span className="text-text-muted text-[10px] uppercase font-semibold">Untrusted User Prompt</span>
            <div className="p-2.5 rounded bg-bg-secondary/50 border border-border-secondary font-mono text-[11px] text-text-secondary max-h-24 overflow-y-auto break-words whitespace-pre-wrap">
              {req.userPrompt}
            </div>
          </div>
        )}

        {req.toolSequence && req.toolSequence.length > 0 && (
          <div className="space-y-1">
            <span className="text-text-muted text-[10px] uppercase font-semibold">Tool Sequence</span>
            <div className="flex flex-wrap gap-1.5 mt-0.5">
              {req.toolSequence.map((tool, idx) => (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded bg-bg-secondary border border-border-secondary font-mono text-[11px] text-text-primary"
                >
                  {tool}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── STAGE 2: INTENT ─────────────────────────────────────────── */}
      <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
        <StageHeader
          stepNumber={2}
          title="Intent"
          badgeText={
            req.intentSource === 'UNTRUSTED_LLM_PARSER'
              ? 'Untrusted Intent Parser (LLM)'
              : 'Deterministic Sequence (Zero-LLM)'
          }
          badgeClass={
            req.intentSource === 'UNTRUSTED_LLM_PARSER'
              ? 'bg-status-warning/15 text-status-warning border-status-warning/30 font-semibold'
              : 'bg-status-info/15 text-status-info border-status-info/30 font-semibold'
          }
        />

        {req.intentSource === 'UNTRUSTED_LLM_PARSER' ? (
          <div className="p-2.5 rounded bg-status-warning/5 border border-status-warning/20 text-[11px] text-text-secondary">
            <span className="font-semibold text-status-warning">LLM Trust Boundary:</span> The LLM converts natural language into structured intent and is treated as an untrusted parser with zero security authority.
          </div>
        ) : (
          <div className="p-2.5 rounded bg-status-info/5 border border-status-info/20 text-[11px] text-text-secondary">
            <span className="font-semibold text-status-info">Deterministic Intent:</span> Executed directly from predefined tool sequence without LLM translation.
          </div>
        )}

        {req.toolInvocation ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px] p-2.5 rounded bg-bg-secondary/40 border border-border-secondary">
            <div>
              <span className="text-text-muted text-[10px] uppercase font-semibold">Target Tool</span>
              <div className="font-mono font-semibold text-text-primary mt-0.5">
                {req.toolInvocation.toolId}
              </div>
            </div>
            <div>
              <span className="text-text-muted text-[10px] uppercase font-semibold">Target Resource</span>
              <div className="font-mono text-text-secondary mt-0.5">
                {req.toolInvocation.resource || '—'}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-text-muted italic">
            No specific tool invocation mapped.
          </div>
        )}
      </div>

      {/* ── STAGE 3: AUTHORIZATION ──────────────────────────────────── */}
      {auth ? (
        <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
          <StageHeader
            stepNumber={3}
            title="Authorization"
            badgeText={auth.decision}
            badgeClass={DECISION_BADGES[auth.decision] || 'bg-bg-secondary text-text-muted'}
          />

          <div className="text-[11px] text-text-secondary">
            <span className="font-semibold text-text-primary">Policy Outcome: </span>
            {auth.reason}
          </div>

          <div className="space-y-1.5 pt-1">
            <span className="text-text-muted text-[10px] uppercase font-semibold tracking-wider">
              Canonical Policy Checks ({auth.checks.length})
            </span>

            <div className="divide-y divide-border-secondary/60 rounded-lg border border-border-secondary overflow-hidden">
              {auth.checks.map((check: ScenarioAuthorizationCheck) => {
                const badgeInfo = CHECK_STATUS_BADGES[check.status] || {
                  label: check.status.toUpperCase(),
                  badge: 'bg-bg-secondary text-text-muted',
                }
                const displayName = check.name || CHECK_KEY_LABELS[check.key] || check.key

                return (
                  <div key={check.key} className="p-2.5 bg-bg-secondary/20 hover:bg-bg-secondary/40 transition-colors space-y-1 text-[11px]">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-text-primary">{displayName}</span>
                        <span className="text-[10px] font-mono text-text-muted">({check.key})</span>
                      </div>
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border ${badgeInfo.badge}`}>
                        {badgeInfo.label}
                      </span>
                    </div>

                    <div className="text-text-secondary text-[11px]">
                      {check.reason}
                    </div>

                    {check.details && Object.keys(check.details).length > 0 && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {Object.entries(check.details).map(([k, v]) => (
                          <span
                            key={k}
                            className="px-1.5 py-0.5 rounded bg-bg-surface border border-border-secondary text-[10px] font-mono text-text-muted"
                          >
                            <span className="text-text-secondary font-medium">{k}:</span> {v}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      ) : (
        <UnreachedStage
          stepNumber={3}
          title="Authorization"
          reason={refusal ? `Skipped due to trust boundary refusal (${refusal}).` : 'Authorization stage was not evaluated.'}
        />
      )}

      {/* ── STAGE 4: DETECTION ──────────────────────────────────────── */}
      {det ? (
        <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
          <StageHeader
            stepNumber={4}
            title="Detection"
            badgeText={`${det.findingCount} ${det.findingCount === 1 ? 'Finding' : 'Findings'}`}
            badgeClass={
              det.findingCount > 0
                ? 'bg-status-warning/15 text-status-warning border-status-warning/30 font-semibold'
                : 'bg-status-active/15 text-status-active border-status-active/30'
            }
          />

          {det.findings.length > 0 ? (
            <div className="space-y-2">
              {det.findings.map((f) => (
                <div
                  key={f.findingId}
                  className="p-2.5 rounded-lg bg-bg-secondary/30 border border-border-secondary space-y-1 text-[11px]"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-text-primary">{f.ruleName}</span>
                      <span className="text-[10px] font-mono text-text-muted">({f.findingId})</span>
                    </div>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider border ${
                        RISK_BADGES[f.severity] || 'bg-bg-secondary text-text-muted border-border-secondary'
                      }`}
                    >
                      {f.severity}
                    </span>
                  </div>
                  <p className="text-text-secondary">{f.description}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-text-muted italic">
              No detection rules were triggered during execution.
            </div>
          )}
        </div>
      ) : (
        <UnreachedStage
          stepNumber={4}
          title="Detection"
          reason={refusal ? `Skipped due to trust boundary refusal (${refusal}).` : 'Detection stage was not evaluated.'}
        />
      )}

      {/* ── STAGE 5: RISK ───────────────────────────────────────────── */}
      {risk ? (
        <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
          <StageHeader
            stepNumber={5}
            title="Risk"
            badgeText={risk.level}
            badgeClass={RISK_BADGES[risk.level] || 'bg-bg-secondary text-text-muted'}
          />

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[11px]">
            <div className="p-2 rounded bg-bg-secondary/40 border border-border-secondary">
              <span className="text-text-muted text-[10px] uppercase font-semibold">Risk Level</span>
              <div className="font-bold text-text-primary mt-0.5">{risk.level}</div>
            </div>
            <div className="p-2 rounded bg-bg-secondary/40 border border-border-secondary">
              <span className="text-text-muted text-[10px] uppercase font-semibold">Risk Score</span>
              <div className="font-mono font-bold text-text-primary mt-0.5">{risk.score}</div>
            </div>
            <div className="p-2 rounded bg-bg-secondary/40 border border-border-secondary">
              <span className="text-text-muted text-[10px] uppercase font-semibold">Finding Count</span>
              <div className="font-mono font-bold text-text-primary mt-0.5">{risk.findingCount}</div>
            </div>
          </div>
        </div>
      ) : (
        <UnreachedStage
          stepNumber={5}
          title="Risk"
          reason={refusal ? `Skipped due to trust boundary refusal (${refusal}).` : 'Risk assessment stage was not evaluated.'}
        />
      )}

      {/* ── STAGE 6: RESPONSE ───────────────────────────────────────── */}
      {resp ? (
        <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
          <StageHeader
            stepNumber={6}
            title="Response"
            badgeText={resp.action}
            badgeClass={RESPONSE_BADGES[resp.action] || 'bg-bg-secondary text-text-muted'}
          />

          <div className="text-[11px] text-text-secondary">
            <span className="font-semibold text-text-primary">Recommended Action: </span>
            <span className="font-mono font-semibold">{resp.action}</span>
          </div>

          <div className="text-[11px] text-text-secondary">
            <span className="font-semibold text-text-primary">Authoritative Rationale: </span>
            {resp.reason}
          </div>
        </div>
      ) : (
        <UnreachedStage
          stepNumber={6}
          title="Response"
          reason={refusal ? `Skipped due to trust boundary refusal (${refusal}).` : 'Response recommendation stage was not evaluated.'}
        />
      )}

      {/* ── STAGE 7: AUDIT ──────────────────────────────────────────── */}
      {audit ? (
        <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
          <StageHeader
            stepNumber={7}
            title="Audit"
            badgeText="Correlated"
            badgeClass="bg-status-active/15 text-status-active border-status-active/30"
          />

          <div className="text-[11px] text-text-secondary flex items-center justify-between">
            <div>
              <span className="font-semibold text-text-primary">Audit Event ID: </span>
              <span className="font-mono font-bold text-accent-primary">{audit.eventId}</span>
            </div>
          </div>
          <p className="text-[10px] text-text-muted">
            Authoritative event_id recorded for this execution.
          </p>
        </div>
      ) : (
        <UnreachedStage
          stepNumber={7}
          title="Audit"
          reason="No audit record was correlated with this execution."
        />
      )}

      {/* ── STAGE 8: FINAL DECISION ─────────────────────────────────── */}
      {finalDec ? (
        <div className="p-3.5 rounded-xl bg-bg-surface border border-border-secondary space-y-3">
          <StageHeader
            stepNumber={8}
            title="Final Decision"
            badgeText={finalDec.decision}
            badgeClass={DECISION_BADGES[finalDec.decision] || 'bg-bg-secondary text-text-muted'}
          />

          <div className="text-[11px] text-text-secondary">
            <span className="font-semibold text-text-primary">Pipeline Outcome: </span>
            <span className="font-mono font-bold">{finalDec.decision}</span>
          </div>

          {decisionsDiffer && (
            <div className="p-2.5 rounded bg-status-warning/10 border border-status-warning/30 text-[11px] text-text-secondary">
              <span className="font-semibold text-status-warning">Decision Variance: </span>
              Initial authorization was <span className="font-mono font-semibold">{auth.decision}</span>, while final pipeline outcome is <span className="font-mono font-semibold">{finalDec.decision}</span>.
            </div>
          )}
        </div>
      ) : (
        <UnreachedStage
          stepNumber={8}
          title="Final Decision"
          reason="Pipeline terminated before establishing a final execution decision."
        />
      )}
    </div>
  )
}
