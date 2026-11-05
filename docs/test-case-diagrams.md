# Test Case Diagrams

These diagrams show the flow and coverage of the synthetic test scenarios. They describe the current prototype and are not policy or production process diagrams.

## Test execution flow

```mermaid
flowchart LR
    A["Synthetic business records"] --> B["PostgreSQL constraints"]
    B --> C{"Test scenario"}
    C --> D["Sales and VAT rules"]
    C --> E["Invoice/customs reconciliation"]
    C --> F["Admin review and audit"]
    D --> G["SQL views and risk reasons"]
    E --> G
    F --> H["Access and audit assertions"]
    G --> I["API/dashboard response"]
    I --> J["Compare observed result with expected result"]
    H --> J
    J --> K["Pass, or record discrepancy for domain review"]
```

## Scenario coverage map

```mermaid
flowchart TB
    subgraph Rules["Business rule scenarios"]
        RT01["RT-01 Monthly sales aggregation"]
        RT02["RT-02 Reconciliation tolerance"]
        RT03["RT-03 Sales threshold boundary"]
        RT04["RT-04 Unmatched source records"]
        RT05["RT-05 Input VAT boundary"]
        RT06["RT-06 Duplicate invoice number"]
    end
    subgraph Safeguards["Operational safeguards"]
        RT07["RT-07 Authorized review and audit"]
        RT08["RT-08 Repeatable startup migrations"]
    end
    Rules --> SQL["Database views and constraints"]
    Safeguards --> AUDIT["API access and audit history"]
    SQL --> ASSERT["Expected-result assertions"]
    AUDIT --> ASSERT
    ASSERT --> HUMAN["Human review; domain validation where assumptions remain"]
```

The RT-IDs correspond to the [recommended executable scenarios](test-scenarios.md#recommended-executable-scenarios). Thresholds and matching behavior remain demonstration assumptions until confirmed against authoritative requirements.
