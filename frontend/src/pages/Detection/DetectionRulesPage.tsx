/**
 * DetectionRulesPage — Active detection rule catalog.
 *
 * ADR-009: "A grid of active security rules (Prompt Injection,
 * Sensitive File Access, Data Exfiltration, etc.) describing
 * their detection categories and descriptions."
 *
 * This is a placeholder.  A future PR will implement the rule
 * grid backed by GET /api/v1/detection/rules.
 */

export default function DetectionRulesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-text-primary">
          Detection Rules
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Active security detection rules mapped to OWASP LLM Top 10 and MITRE ATLAS/ATT&CK.
        </p>
      </div>

      {/* Rule card placeholders */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[
          {
            name: 'Prompt Injection',
            category: 'PROMPT_SECURITY',
            description: 'Detects user prompt injection attempts targeting LLM instruction override.',
          },
          {
            name: 'Sensitive File Access',
            category: 'DATA_SECURITY',
            description: 'Detects attempts to access sensitive filesystem paths.',
          },
          {
            name: 'Data Exfiltration',
            category: 'DATA_SECURITY',
            description: 'Detects attempts to exfiltrate data to external destinations.',
          },
        ].map((rule) => (
          <div
            key={rule.name}
            className="bg-bg-surface border border-border-secondary rounded-xl p-5 space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-text-primary">
                {rule.name}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent-primary/10 text-accent-primary">
                {rule.category}
              </span>
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">
              {rule.description}
            </p>
            <div className="text-[10px] text-text-muted">
              Security framework mappings will be shown after API integration.
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
