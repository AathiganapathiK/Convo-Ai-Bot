import React, { useState } from "react";
import { 
  Card, Row, Col, Input, Button, Steps, Typography, 
  Badge, Divider, Space, Collapse, Alert 
} from "antd";
import { 
  PlayCircleOutlined, CheckCircleOutlined, 
  NodeIndexOutlined, FileSearchOutlined, LockOutlined, ConsoleSqlOutlined, 
  DatabaseOutlined, DashboardOutlined 
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Panel } = Collapse;

export default function QueryPipelineDebugger() {
  const [question, setQuestion] = useState("What were the sales for products in VIP customer tier?");
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(-1);
  const [showResults, setShowResults] = useState(false);

  const handleRunTrace = () => {
    setLoading(true);
    setCurrentStep(0);
    setShowResults(true);

    const runStages = [
      () => setCurrentStep(1),
      () => setCurrentStep(2),
      () => setCurrentStep(3),
      () => setCurrentStep(4),
      () => setCurrentStep(5),
      () => setCurrentStep(6),
      () => setLoading(false)
    ];

    runStages.forEach((stageFn, idx) => {
      setTimeout(stageFn, (idx + 1) * 800);
    });
  };

  const stepsData = [
    {
      title: "Intent Classification",
      subtitle: "intent_classifier.py",
      icon: <NodeIndexOutlined />,
      log: "[INFO] Classifying query intent...\n[LOG] Running prompt on Llama-3-70b-specdec\n[RESULT] Intent classified as: DATABASE\n[METRIC] Classification latency: 240ms"
    },
    {
      title: "Context Generation",
      subtitle: "prompt_builder.py",
      icon: <FileSearchOutlined />,
      log: "[INFO] Building SQL Prompt...\n[LOG] Injecting table definition: sales_trans (transaction_id, sales_amount, salesperson_id, region)\n[LOG] Injecting table definition: customers (customer_id, customer_name, region, tier)\n[LOG] Injected 3 semantic definitions."
    },
    {
      title: "SQL Code Generation",
      subtitle: "ai_service.py",
      icon: <ConsoleSqlOutlined />,
      log: "[INFO] Running Text-to-SQL compiler...\n[LOG] LLM prompt successfully resolved.\n[RESULT] Generated SQL query:\nSELECT c.tier, SUM(s.sales_amount) as total_sales \nFROM sales_trans s \nJOIN customers c ON s.customer_id = c.customer_id \nGROUP BY c.tier;"
    },
    {
      title: "Row-Level Security (RLS)",
      subtitle: "rls_engine.py",
      icon: <LockOutlined />,
      log: "[INFO] Injecting row governance policies...\n[LOG] Fetching data access for user: analyst_east (region = 'East')\n[RESULT] Re-engineered SQL query:\nSELECT c.tier, SUM(s.sales_amount) as total_sales \nFROM sales_trans s \nJOIN customers c ON s.customer_id = c.customer_id \nWHERE s.region = 'East' \nGROUP BY c.tier;"
    },
    {
      title: "Column-Level Security (CLS)",
      subtitle: "cls_engine.py",
      icon: <LockOutlined />,
      log: "[INFO] Performing static SQL AST column audit...\n[LOG] Auditing requested columns: [c.tier, s.sales_amount]\n[LOG] Verification: OK (Columns are permitted for role ANALYST)"
    },
    {
      title: "Database Query Runner",
      subtitle: "sql_validator.py",
      icon: <DatabaseOutlined />,
      log: "[INFO] Executing on SQL Server (dw-prod-01)...\n[LOG] sp_set_session_context set to Role = ANALYST\n[LOG] Fetching cursor...\n[RESULT] Query execution succeeded. Rowcount: 3 rows."
    },
    {
      title: "Visual Explanation Recommendations",
      subtitle: "chart_generator.py",
      icon: <DashboardOutlined />,
      log: "[INFO] Running data layout evaluation...\n[LOG] Categorical key detected: [tier]\n[LOG] Numerical measure detected: [total_sales]\n[RESULT] Recommended visualization: BAR_CHART\n[LOG] Generating business insights summary."
    }
  ];

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ marginBottom: "24px" }}>
        <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
          Query Pipeline Debugger
        </Title>
        <Text style={{ color: "var(--text-muted)" }}>
          Examine the backend SQL generation pipeline. Traces how input queries are modified, audited, and formatted.
        </Text>
      </div>

      <Row gutter={[16, 16]}>
        {/* Top Input Control */}
        <Col span={24}>
          <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
            <div style={{ display: "flex", gap: "12px" }}>
              <Input 
                value={question} 
                onChange={e => setQuestion(e.target.value)}
                placeholder="Enter query to trace..."
                style={{ background: "var(--border-color)", border: "1px solid var(--border-light)" }} 
              />
              <Button 
                type="primary" 
                icon={<PlayCircleOutlined />} 
                onClick={handleRunTrace} 
                loading={loading}
                style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
              >
                Trigger Pipeline Trace
              </Button>
            </div>
          </Card>
        </Col>

        {showResults && (
          <>
            {/* Left Side: Pipeline Stepper */}
            <Col xs={24} md={10}>
              <Card 
                title={<span style={{ color: "var(--text-main)" }}><ConsoleSqlOutlined /> Execution Steps</span>}
                bordered={false} 
                style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}
              >
                <Steps
                  direction="vertical"
                  current={currentStep}
                  items={stepsData.map((step, idx) => {
                    let status = "wait";
                    if (currentStep > idx) status = "finish";
                    if (currentStep === idx) status = loading ? "process" : "finish";
                    return {
                      title: <span style={{ color: "var(--text-main)", fontWeight: 600 }}>{step.title}</span>,
                      description: <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>{step.subtitle}</span>,
                      icon: step.icon,
                      status: status
                    };
                  })}
                />
              </Card>
            </Col>

            {/* Right Side: Log Console Output */}
            <Col xs={24} md={14}>
              <Card 
                title={
                  <div style={{ display: "flex", justifyContent: "space-between", width: "100%" }}>
                    <span style={{ color: "var(--text-main)" }}><ConsoleSqlOutlined /> Console Stream Output</span>
                    {loading ? <Badge status="processing" text="Tracing active" /> : <Badge status="success" text="Trace Complete" />}
                  </div>
                }
                bordered={false}
                style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}
              >
                <div style={{ background: "var(--bg-layout)", padding: "16px", borderRadius: "8px", border: "1px solid var(--border-color)", minHeight: "440px" }}>
                  <Collapse ghost defaultActiveKey={["0", "1", "2", "3", "4", "5", "6"]}>
                    {stepsData.map((step, idx) => {
                      if (currentStep < idx) return null;
                      return (
                        <Panel 
                          header={
                            <div style={{ display: "flex", justify: "space-between", width: "100%" }}>
                              <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>[Step {idx + 1}] {step.title}</span>
                              <span style={{ color: "#6b7280", fontSize: "11px", fontFamily: "monospace" }}>{step.subtitle}</span>
                            </div>
                          } 
                          key={idx}
                        >
                          <pre style={{ 
                            color: "var(--text-active)", 
                            fontFamily: "monospace", 
                            fontSize: "12px", 
                            margin: 0,
                            whiteSpace: "pre-wrap"
                          }}>
                            {step.log}
                          </pre>
                        </Panel>
                      );
                    })}
                  </Collapse>
                </div>
              </Card>
            </Col>
          </>
        )}
      </Row>
    </div>
  );
}
