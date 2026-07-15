import React, { useState } from "react";
import { 
  Row, Col, Card, Select, Button, Space, Typography, 
  Input, Tabs, Divider, Tag, List, Badge, message 
} from "antd";
import { 
  CodeOutlined, SaveOutlined, PlayCircleOutlined, HistoryOutlined, 
  DatabaseOutlined, BulbOutlined 
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { TextArea } = Input;

const initialPrompts = {
  sql_gen: {
    name: "SQL Generation Prompt",
    version: "v2.1.4",
    lastUpdated: "2026-06-12 14:00 by SystemAdmin",
    systemPrompt: `You are an expert SQL generator. Given a user question, database schema, and historical chat context, write a valid Microsoft SQL Server query that returns the requested information.

[DATABASE SCHEMA]
{schema_context}

[SEMANTIC RULES]
{semantic_context}

[ROW LEVEL SECURITY CONTEXT]
Active Department Context: {user_department}
Active Role Context: {user_role}

[INSTRUCTIONS]
1. Write ONLY the executable SQL query. Do not wrap in markdown quotes.
2. Order results clearly. Always use TOP 500 if no row limit is specified.
3. Only use tables listed in schema context. Do not make up tables.
4. Avoid selecting sensitive columns listed as BLOCKED.`,
    variables: ["{schema_context}", "{semantic_context}", "{user_department}", "{user_role}", "{question}", "{history}"]
  },
  insight_gen: {
    name: "Business Insight Summary",
    version: "v1.8.0",
    lastUpdated: "2026-06-10 11:20 by AnalyticsLead",
    systemPrompt: `You are a professional business intelligence analyst. Summarize the query results and formulate a readable business response.

[USER QUESTION]
{question}

[GENERATED SQL]
{sql_query}

[DATASET RETURNED]
{dataset_json}

[GUIDELINES]
1. Keep the explanation action-oriented and brief.
2. Format metrics in clear USD, percentage, or count units.
3. List key takeaways in bullet points.`,
    variables: ["{question}", "{sql_query}", "{dataset_json}"]
  }
};

export default function PromptStudio() {
  const [selectedPromptKey, setSelectedPromptKey] = useState("sql_gen");
  const [currentPrompt, setCurrentPrompt] = useState(initialPrompts.sql_gen);
  const [systemText, setSystemText] = useState(initialPrompts.sql_gen.systemPrompt);
  const [previewResolved, setPreviewResolved] = useState("");
  const [testQuestion, setTestQuestion] = useState("What were the sales for products in VIP customer tier?");

  const handleSelectPrompt = (key) => {
    setSelectedPromptKey(key);
    setCurrentPrompt(initialPrompts[key]);
    setSystemText(initialPrompts[key].systemPrompt);
    setPreviewResolved("");
  };

  const handleSavePrompt = () => {
    message.success(`Prompt template "${currentPrompt.name}" saved as a new version!`);
  };

  const handleResolvePreview = () => {
    let resolved = systemText;
    
    // Simulate resolving the variables
    if (selectedPromptKey === "sql_gen") {
      resolved = resolved
        .replace("{schema_context}", "TABLE sales_trans (transaction_id BIGINT, sales_amount DECIMAL, region VARCHAR)")
        .replace("{semantic_context}", "Net Revenue formula is SUM(sales_amount)")
        .replace("{user_department}", "Sales")
        .replace("{user_role}", "Analyst")
        .replace("{question}", testQuestion)
        .replace("{history}", "[]");
    } else {
      resolved = resolved
        .replace("{question}", testQuestion)
        .replace("{sql_query}", "SELECT TOP 100 * FROM sales_trans")
        .replace("{dataset_json}", "[{transaction_id: 100, sales_amount: 142.5}]");
    }

    setPreviewResolved(resolved);
  };

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            Prompt Studio
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Design, evaluate, and test LLM instructions. Inspect variable resolution and preview resolved prompt outputs.
          </Text>
        </div>
        <Space>
          <Button 
            type="primary" 
            icon={<SaveOutlined />}
            style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
            onClick={handleSavePrompt}
          >
            Save Template
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        {/* Left Side: Selector and Prompt Editor */}
        <Col xs={24} lg={14}>
          <Card 
            title={
              <Space>
                <CodeOutlined style={{ color: "#6366f1" }} />
                <Select 
                  value={selectedPromptKey} 
                  onChange={handleSelectPrompt}
                  dropdownStyle={{ background: "var(--border-color)" }}
                  style={{ width: 240 }}
                >
                  <Option value="sql_gen">SQL Generation Prompt</Option>
                  <Option value="insight_gen">Business Insight Summary</Option>
                </Select>
                <Tag color="geekblue">{currentPrompt.version}</Tag>
              </Space>
            }
            extra={
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                Updated: {currentPrompt.lastUpdated}
              </span>
            }
            bordered={false}
            style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", minHeight: "600px" }}
          >
            <div style={{ marginBottom: "16px" }}>
              <Text style={{ color: "var(--text-muted)", display: "block", marginBottom: "8px" }}>System Instruction Template</Text>
              <TextArea
                value={systemText}
                onChange={e => setSystemText(e.target.value)}
                rows={18}
                style={{ 
                  fontFamily: "monospace", 
                  background: "var(--bg-chat-input)", 
                  border: "1px solid var(--border-chat-input)", 
                  color: "var(--text-main)",
                  fontSize: "13px",
                  lineHeight: "1.5"
                }}
              />
            </div>

            <div>
              <Text style={{ color: "var(--text-muted)", display: "block", marginBottom: "8px" }}>Available Input Tokens</Text>
              <Space size={[4, 8]} wrap>
                {currentPrompt.variables.map(variable => (
                  <Tag key={variable} color="purple" bordered={false} style={{ fontFamily: "monospace" }}>{variable}</Tag>
                ))}
              </Space>
            </div>
          </Card>
        </Col>

        {/* Right Side: Resolve Sandbox and Versioning */}
        <Col xs={24} lg={10}>
          <Card 
            title={<span style={{ color: "var(--text-main)" }}><PlayCircleOutlined /> Preview & Testing Sandbox</span>}
            bordered={false}
            style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", minHeight: "600px" }}
            bodyStyle={{ display: "flex", flexDirection: "column", height: "calc(100% - 56px)" }}
          >
            <div style={{ marginBottom: "16px" }}>
              <Text style={{ color: "var(--text-muted)", display: "block", marginBottom: "8px" }}>Sample User Input (For Test Resolution)</Text>
              <Input 
                value={testQuestion} 
                onChange={e => setTestQuestion(e.target.value)}
                style={{ background: "var(--bg-chat-input)", border: "1px solid var(--border-chat-input)" }} 
              />
              <Button 
                type="primary" 
                icon={<PlayCircleOutlined />} 
                onClick={handleResolvePreview} 
                style={{ marginTop: "12px", width: "100%" }}
              >
                Compile & Resolve Variables
              </Button>
            </div>

            <Divider style={{ borderColor: "var(--border-color)", margin: "16px 0" }} />

            <div style={{ flex: 1 }}>
              <Text style={{ color: "var(--text-muted)", display: "block", marginBottom: "8px" }}>Compiled Output Prompt (Sent to LLM Provider)</Text>
              {previewResolved ? (
                <TextArea
                  readOnly
                  value={previewResolved}
                  rows={13}
                  style={{ 
                    fontFamily: "monospace", 
                    background: "var(--bg-layout)", 
                    border: "1px solid var(--border-color)", 
                    color: "var(--text-active)",
                    fontSize: "11px",
                    lineHeight: "1.4"
                  }}
                />
              ) : (
                <div style={{ 
                  height: "260px", 
                  background: "var(--bg-layout)", 
                  borderRadius: "8px", 
                  display: "flex", 
                  alignItems: "center", 
                  justifyContent: "center",
                  border: "1px dashed var(--border-light)" 
                }}>
                  <span style={{ color: "var(--text-muted)" }}><BulbOutlined /> Click "Compile" above to inspect output</span>
                </div>
              )}
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
