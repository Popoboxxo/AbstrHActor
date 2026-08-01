# Graph Report - .  (2026-08-01)

## Corpus Check
- 14 files · ~8,361 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 66 nodes · 94 edges · 7 communities
- Extraction: 77% EXTRACTED · 22% INFERRED · 1% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Integration Core & Devices
- Lastenheft & Metering
- Agent Orchestration & Rules
- Sensor Strategy Types
- Agent-meta & Memory
- Knowledge Engine & Wiki
- Bridge Implementations

## God Nodes (most connected - your core abstractions)
1. `AbstrHActor Project` - 27 edges
2. `Lastenheft: Energy Abstraction Layer as Custom Integration` - 13 edges
3. `AGENTS.md agent instructions` - 10 edges
4. `Strategy Pattern (AbstractSensor)` - 7 edges
5. `AbstractSensor interface` - 7 edges
6. `Bridge Pattern` - 6 edges
7. `AbstractBridge protocol` - 5 edges
8. `CLAUDE.md project context (agent-meta generated)` - 5 edges
9. `agent-meta framework` - 4 edges
10. `Python custom integration approach` - 4 edges

## Surprising Connections (you probably didn't know these)
- `Serena project configuration (AbstrHActor)` --semantically_similar_to--> `AbstrHActor Project`  [INFERRED] [semantically similar]
  .serena/project.yml → .meta-config/project.yaml
- `CLAUDE.md project context (agent-meta generated)` --semantically_similar_to--> `AbstrHActor Project`  [INFERRED] [semantically similar]
  CLAUDE.md → .meta-config/project.yaml
- `README (AbstrHActor)` --semantically_similar_to--> `AbstrHActor Project`  [INFERRED] [semantically similar]
  README.md → .meta-config/project.yaml
- `Branch-Guard rule` --conceptually_related_to--> `AbstrHActor Project`  [INFERRED]
  AGENTS.md → .meta-config/project.yaml
- `Config-Flow device onboarding (FA-01)` --semantically_similar_to--> `Config Flow with stable Unique ID`  [INFERRED] [semantically similar]
  LASTENHEFT_ABSTRAKTIONS_INTEGRATION.md → .meta-config/project.yaml

## Hyperedges (group relationships)
- **Bridge implementations of the AbstractBridge protocol** — _meta_config_project_bridge_pattern, _meta_config_project_abstractbridge, _meta_config_project_serialbridge, _meta_config_project_mqttbridge, _meta_config_project_httpbridge [INFERRED 0.85]
- **Sensor types implementing the Strategy/AbstractSensor pattern** — _meta_config_project_strategy_pattern, _meta_config_project_abstractsensor, _meta_config_project_temperature, _meta_config_project_humidity, _meta_config_project_pressure, _meta_config_project_power, _meta_config_project_water [INFERRED 0.85]
- **YAML abstraction packages targeted for migration to the Python integration** — lastenheft_abstraktions_integration_energypower, lastenheft_abstraktions_integration_batterypower, lastenheft_abstraktions_integration_ace1500, lastenheft_abstraktions_integration_waterconsumption, lastenheft_abstraktions_integration_pythonintegration [INFERRED 0.85]

## Communities (7 total, 0 thin omitted)

### Community 0 - "Integration Core & Devices"
Cohesion: 0.14
Nodes (15): AbstrHActor Project, Adapter Pattern (HA native entity registry), DataUpdateCoordinator central polling, DeviceRegistry, DoD Preset: rapid-prototyping, EntityDescription declarative sensor types, HACS Delivery, Home Assistant platform (+7 more)

### Community 1 - "Lastenheft & Metering"
Cohesion: 0.16
Nodes (15): Config Flow with stable Unique ID, Spike Filter / Monotonic Guard, ace1500_power_energy.yaml abstraction (Zendure ACE 1500), Codebase Audit 2026-07-29 (docs/AUDIT_HA_2026-07-29.md), battery_power_energy.yaml abstraction (Hyper2000), Config-Flow device onboarding (FA-01), energy_power.yaml abstraction (117 sensors), HA Core Entity Aliasing request (Discussions #3402) (+7 more)

### Community 2 - "Agent Orchestration & Rules"
Cohesion: 0.22
Nodes (10): Orchestrator agent role, ReqogniLoom MCP server, A2A Anti-Re-Delegation Gates, AGENTS.md agent instructions, Agent Directory, Branch-Guard rule, Conventional Commits convention, CRITICAL GATE (orchestrator-only edits) (+2 more)

### Community 3 - "Sensor Strategy Types"
Cohesion: 0.52
Nodes (7): AbstractSensor interface, Humidity sensor type, Power sensor type, Pressure sensor type, Strategy Pattern (AbstractSensor), Temperature sensor type, Water sensor type

### Community 4 - "Agent-meta & Memory"
Cohesion: 0.43
Nodes (7): agent-meta framework, Serena memory maintenance conventions, mem:core graph root, Progressive memory discovery graph, mem: prefixed memory references, CLAUDE.md project context (agent-meta generated), agent-meta managed configuration block

### Community 5 - "Knowledge Engine & Wiki"
Cohesion: 0.33
Nodes (7): Knowledge Engine (internal-docs), AGENTS.md Knowledge Engine section, CLAUDE.md Knowledge Engine section, OKF concept types (concept, architecture, guide, reference), Knowledge Schema (internal-docs), Knowledge Index (index.md), Knowledge Log (log.md, append-only)

### Community 6 - "Bridge Implementations"
Cohesion: 0.70
Nodes (5): AbstractBridge protocol, Bridge Pattern, HTTP Bridge, MQTT Bridge, Serial Bridge

## Ambiguous Edges - Review These
- `CLAUDE.md project context (agent-meta generated)` → `mem:core graph root`  [AMBIGUOUS]
  .serena/memories/memory_maintenance.md · relation: conceptually_related_to

## Knowledge Gaps
- **14 isolated node(s):** `Home Assistant platform`, `DoD Preset: rapid-prototyping`, `Zendure hardware`, `Shelly hardware`, `Tasmota hardware` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `CLAUDE.md project context (agent-meta generated)` and `mem:core graph root`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `AbstrHActor Project` connect `Integration Core & Devices` to `Lastenheft & Metering`, `Agent Orchestration & Rules`, `Sensor Strategy Types`, `Agent-meta & Memory`, `Knowledge Engine & Wiki`, `Bridge Implementations`?**
  _High betweenness centrality (0.834) - this node is a cross-community bridge._
- **Why does `Lastenheft: Energy Abstraction Layer as Custom Integration` connect `Lastenheft & Metering` to `Integration Core & Devices`?**
  _High betweenness centrality (0.258) - this node is a cross-community bridge._
- **Why does `AGENTS.md agent instructions` connect `Agent Orchestration & Rules` to `Agent-meta & Memory`, `Knowledge Engine & Wiki`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `AbstrHActor Project` (e.g. with `Bridge Pattern` and `Config Flow with stable Unique ID`) actually correct?**
  _`AbstrHActor Project` has 11 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Home Assistant platform`, `DoD Preset: rapid-prototyping`, `Zendure hardware` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Integration Core & Devices` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._