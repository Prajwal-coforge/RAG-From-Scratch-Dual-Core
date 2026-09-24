// Schema preview only. These nodes are not ingested policy text.
// schema_sample = true so they can be removed before real ingestion.

CREATE CONSTRAINT ON (n:Policy) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:PolicyVersion) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Section) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Chunk) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Role) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Department) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Control) ASSERT n.id IS UNIQUE;

CREATE VECTOR INDEX chunk_embedding ON :Chunk(embedding) WITH CONFIG {"dimension": 768, "capacity": 10000, "metric": "cos"};

CREATE (bag:Policy {
  id: "schema:policy:AP-BAG-001",
  tenant_id: "aeropolicy-demo",
  corpus_id: "airport-generated",
  policy_id: "AP-BAG-001",
  title: "Staff Baggage Handling and Escalation",
  schema_sample: true
})
CREATE (bagV2:PolicyVersion {
  id: "schema:version:AP-BAG-001:v2",
  version: "v2",
  effective_from: "2025-07-01",
  publication_status: "current",
  schema_sample: true
})
CREATE (bagV1:PolicyVersion {
  id: "schema:version:AP-BAG-001:v1",
  version: "v1",
  effective_from: "2025-01-01",
  effective_to: "2025-06-30",
  publication_status: "obsolete",
  schema_sample: true
})
CREATE (escalation:Section {
  id: "schema:section:AP-BAG-001:escalation",
  heading_path: "Escalation",
  schema_sample: true
})
CREATE (exception:Section {
  id: "schema:section:AP-BAG-001:exception",
  heading_path: "Exception",
  schema_sample: true
})
CREATE (chunk:Chunk {
  id: "schema:chunk:AP-BAG-001:escalation",
  schema_sample: true
})
CREATE (incident:Policy {
  id: "schema:policy:AP-INC-002",
  tenant_id: "aeropolicy-demo",
  corpus_id: "airport-generated",
  policy_id: "AP-INC-002",
  title: "Operational Incident Response and Review",
  schema_sample: true
})
CREATE (incidentV1:PolicyVersion {
  id: "schema:version:AP-INC-002:v1",
  version: "v1",
  publication_status: "current",
  schema_sample: true
})
CREATE (review:Section {
  id: "schema:section:AP-INC-002:review",
  heading_path: "Review",
  schema_sample: true
})
CREATE (supervisor:Role {
  id: "schema:role:supervisor",
  name: "supervisor",
  schema_sample: true
})
CREATE (deadline:Control {
  id: "schema:control:escalation-deadline",
  name: "escalation-deadline",
  schema_sample: true
})
CREATE (baggage:Department {
  id: "schema:department:baggage",
  name: "Baggage Operations",
  schema_sample: true
})
CREATE (bag)-[:HAS_VERSION {schema_sample: true}]->(bagV2)
CREATE (bag)-[:HAS_VERSION {schema_sample: true}]->(bagV1)
CREATE (bagV2)-[:SUPERSEDES {schema_sample: true, validation_status: "schema-preview"}]->(bagV1)
CREATE (bagV2)-[:HAS_SECTION {schema_sample: true}]->(escalation)
CREATE (bagV2)-[:HAS_SECTION {schema_sample: true}]->(exception)
CREATE (escalation)-[:HAS_CHUNK {schema_sample: true}]->(chunk)
CREATE (incident)-[:HAS_VERSION {schema_sample: true}]->(incidentV1)
CREATE (incidentV1)-[:HAS_SECTION {schema_sample: true}]->(review)
CREATE (escalation)-[:REFERENCES {schema_sample: true, validation_status: "schema-preview"}]->(review)
CREATE (exception)-[:EXCEPTION_TO {schema_sample: true, validation_status: "schema-preview"}]->(escalation)
CREATE (escalation)-[:APPLIES_TO_ROLE {schema_sample: true, validation_status: "schema-preview"}]->(supervisor)
CREATE (escalation)-[:MAPS_TO_CONTROL {schema_sample: true, validation_status: "schema-preview"}]->(deadline);
