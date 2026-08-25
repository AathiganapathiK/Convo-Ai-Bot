import React, { useState } from "react";
import { 
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, Select, Tabs, Divider, Alert 
} from "antd";
import { message } from "../utils/message";
import { 
  PlusOutlined, NodeIndexOutlined, CompassOutlined, EditOutlined, 
  DeleteOutlined, CheckCircleOutlined, ExclamationCircleOutlined 
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

export default function IntentConfig() {
  const [rules, setRules] = useState([
    {
      key: "r1",
      keyword: "hello",
      target_intent: "GENERAL",
      description: "Directs greetings straight to the conversational assistant."
    },
    {
      key: "r2",
      keyword: "help",
      target_intent: "GENERAL",
      description: "Redirects system usage queries to natural guidelines."
    },
    {
      key: "r3",
      keyword: "select",
      target_intent: "DATABASE",
      description: "Bypasses LLM classifier when explicit query syntax is detected."
    }
  ]);

  const [logs, setLogs] = useState([
    {
      key: "l1",
      timestamp: "2026-06-15 12:02:11",
      input_text: "What were our top items yesterday?",
      detected_intent: "DATABASE",
      confidence: 0.98,
      rule_triggered: "LLM Model (Llama-3)"
    },
    {
      key: "l2",
      timestamp: "2026-06-15 11:58:05",
      input_text: "Hey, can you help me explain the dashboard?",
      detected_intent: "GENERAL",
      confidence: 1.00,
      rule_triggered: "Keyword Override: help"
    },
    {
      key: "l3",
      timestamp: "2026-06-15 11:40:42",
      input_text: "Give me an executive table overview",
      detected_intent: "DATABASE",
      confidence: 0.91,
      rule_triggered: "LLM Model (Llama-3)"
    }
  ]);

  const [isModalVisible, setIsModalVisible] = useState(false);
  const [form] = Form.useForm();

  const handleCreateRule = (values) => {
    const newRule = {
      key: Date.now().toString(),
      keyword: values.keyword.toLowerCase(),
      target_intent: values.target_intent,
      description: values.description
    };
    setRules(prev => [...prev, newRule]);
    message.success(`Intent override rule for "${values.keyword}" added!`);
    setIsModalVisible(false);
    form.resetFields();
  };

  const columns = [
    {
      title: "Keyword / Trigger Prefix",
      dataIndex: "keyword",
      key: "keyword",
      render: (text) => <code style={{ color: "var(--code-pink)" }}>{text}</code>
    },
    {
      title: "Routed Intent",
      dataIndex: "target_intent",
      key: "target_intent",
      render: (text) => {
        let color = "blue";
        if (text === "DATABASE") color = "purple";
        if (text === "GENERAL") color = "green";
        return <Tag color={color} bordered={false}>{text}</Tag>;
      }
    },
    {
      title: "Rule Description",
      dataIndex: "description",
      key: "description",
      render: (text) => <span style={{ color: "var(--text-muted)", fontSize: "13px" }}>{text}</span>
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space>
          <Button 
            type="text" 
            danger 
            icon={<DeleteOutlined />} 
            onClick={() => {
              setRules(prev => prev.filter(r => r.key !== record.key));
              message.success("Keyword override rule removed");
            }}
          />
        </Space>
      )
    }
  ];

  const logColumns = [
    {
      title: "Timestamp",
      dataIndex: "timestamp",
      key: "timestamp",
      render: (text) => <span style={{ color: "#6b7280" }}>{text}</span>
    },
    {
      title: "Incoming Phrase",
      dataIndex: "input_text",
      key: "input_text",
      render: (text) => <span style={{ color: "var(--text-main)" }}>"{text}"</span>
    },
    {
      title: "Classified Intent",
      dataIndex: "detected_intent",
      key: "detected_intent",
      render: (text) => (
        <Tag color={text === "DATABASE" ? "purple" : "green"} bordered={false}>
          {text}
        </Tag>
      )
    },
    {
      title: "Confidence Score",
      dataIndex: "confidence",
      key: "confidence",
      render: (num) => (
        <span style={{ color: num > 0.9 ? "#10b981" : "#f59e0b", fontWeight: 600 }}>
          {(num * 100).toFixed(0)}%
        </span>
      )
    },
    {
      title: "Classification Source",
      dataIndex: "rule_triggered",
      key: "rule_triggered",
      render: (text) => <span style={{ color: "var(--text-muted)" }}>{text}</span>
    }
  ];

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            Intent Configuration
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Add static triggers that override the machine learning models when calculating user query intent.
          </Text>
        </div>
        <Button 
          type="primary" 
          icon={<PlusOutlined />}
          style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
          onClick={() => setIsModalVisible(true)}
        >
          Add Keyword Trigger
        </Button>
      </div>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Tabs 
          items={[
            {
              key: "overrides",
              label: <span style={{ color: "var(--text-main)" }}><NodeIndexOutlined /> Keyword Overrides</span>,
              children: (
                <Table 
                  dataSource={rules} 
                  columns={columns} 
                  pagination={false}
                  style={{ background: "var(--bg-card)" }}
                  className="dark-table"
                />
              )
            },
            {
              key: "logs",
              label: <span style={{ color: "var(--text-main)" }}><CompassOutlined /> Classifier Event Log</span>,
              children: (
                <Table 
                  dataSource={logs} 
                  columns={logColumns} 
                  pagination={{ pageSize: 5 }}
                  style={{ background: "var(--bg-card)" }}
                  className="dark-table"
                />
              )
            }
          ]}
        />
      </Card>

      {/* Override Creation Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Add Keyword Intent Override</span>}
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={null}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateRule}
        >
          <Form.Item
            name="keyword"
            label={<span style={{ color: "var(--text-secondary)" }}>Trigger Phrase / Keyword</span>}
            rules={[{ required: true }]}
            extra={<span style={{ color: "#6b7280", fontSize: "11px" }}>If user query starts with or contains this exact phrase.</span>}
          >
            <Input placeholder="e.g. transaction list" />
          </Form.Item>

          <Form.Item
            name="target_intent"
            label={<span style={{ color: "var(--text-secondary)" }}>Direct Routed Intent</span>}
            rules={[{ required: true }]}
          >
            <Select>
              <Option value="DATABASE">DATABASE (SQL query execution path)</Option>
              <Option value="GENERAL">GENERAL (Conversational feedback loop)</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="description"
            label={<span style={{ color: "var(--text-secondary)" }}>Override Description</span>}
          >
            <Input.TextArea placeholder="Describe the purpose of this override." rows={2} />
          </Form.Item>

          <Divider style={{ borderColor: "var(--border-color)", margin: "16px 0" }} />

          <Form.Item style={{ margin: 0, textAlign: "right" }}>
            <Space>
              <Button onClick={() => setIsModalVisible(false)}>
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                Add Trigger Rule
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
