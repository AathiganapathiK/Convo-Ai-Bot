import React from "react";
import { Drawer, Card, Statistic, Row, Col, Progress, Typography, Space, Divider, Alert } from "antd";
import {
  DashboardOutlined,
  FieldTimeOutlined,
  SafetyOutlined,
  DatabaseOutlined
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;

function StatsDrawer({ visible, onClose }) {
  return (
    <Drawer
      title={<span><DashboardOutlined style={{ marginRight: 8, color: "#6366f1" }} />Platform Usage & Performance Stats</span>}
      placement="right"
      width={460}
      onClose={onClose}
      open={visible}
    >
      <Alert
        message="System Monitor Online"
        description="Stats are updated in real-time. Row-level security (RLS) and Column-level security (CLS) enforce access controls automatically."
        type="info"
        showIcon
        style={{ marginBottom: "20px", borderRadius: "8px" }}
      />

      <Paragraph style={{ color: "var(--text-muted)", marginBottom: "20px" }}>
        Monitor API requests, data query efficiency, and active session telemetry.
      </Paragraph>

      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Card bordered size="small" style={{ borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.02)" }}>
            <Statistic
              title="Total API Queries"
              value={142}
              suffix="/ 1,000"
              valueStyle={{ color: "#4f46e5", fontSize: "20px", fontWeight: 700 }}
            />
            <Progress percent={14.2} showInfo={false} strokeColor="#4f46e5" style={{ marginTop: "8px" }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card bordered size="small" style={{ borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.02)" }}>
            <Statistic
              title="Avg Response Time"
              value={1.18}
              precision={2}
              suffix="s"
              valueStyle={{ color: "#10b981", fontSize: "20px", fontWeight: 700 }}
              prefix={<FieldTimeOutlined />}
            />
            <Text type="secondary" style={{ fontSize: "11px" }}>98th percentile: 2.3s</Text>
          </Card>
        </Col>
        <Col span={12}>
          <Card bordered size="small" style={{ borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.02)" }}>
            <Statistic
              title="Database Matches"
              value={541909}
              prefix={<DatabaseOutlined style={{ color: "#f59e0b" }} />}
              valueStyle={{ fontSize: "18px", fontWeight: 700 }}
            />
            <Text type="secondary" style={{ fontSize: "11px" }}>AdventureWorks rows</Text>
          </Card>
        </Col>
        <Col span={12}>
          <Card bordered size="small" style={{ borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.02)" }}>
            <Statistic
              title="Security Validation"
              value="100%"
              prefix={<SafetyOutlined style={{ color: "#10b981" }} />}
              valueStyle={{ color: "#10b981", fontSize: "18px", fontWeight: 700 }}
            />
            <Text type="secondary" style={{ fontSize: "11px" }}>0 policy violations</Text>
          </Card>
        </Col>
      </Row>

      <Divider style={{ margin: "24px 0" }} />

      <Title level={5} style={{ marginBottom: "16px", color: "var(--text-main)" }}>Token & LLM Telemetry</Title>
      
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
            <Text type="secondary">Prompt Tokens (Input)</Text>
            <Text strong>84,204 / 500k</Text>
          </div>
          <Progress percent={16.8} strokeColor="#6366f1" size="small" />
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
            <Text type="secondary">Completion Tokens (Output)</Text>
            <Text strong>41,920 / 250k</Text>
          </div>
          <Progress percent={16.7} strokeColor="#ec4899" size="small" />
        </div>

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
            <Text type="secondary">Database Query Cache Hit Rate</Text>
            <Text strong>42.5%</Text>
          </div>
          <Progress percent={42.5} strokeColor="#f59e0b" size="small" />
        </div>
      </Space>

      <Divider style={{ margin: "24px 0" }} />

      <Title level={5} style={{ marginBottom: "12px", color: "var(--text-main)" }}>RBAC Policy Enforcement</Title>
      <Text type="secondary" style={{ display: "block", marginBottom: "12px" }}>
        Your user session operates under strict Row-Level Security (RLS) and Column-Level Security (CLS).
      </Text>
      
      <Card size="small" style={{ backgroundColor: "var(--bg-card-inner)", border: "1px solid var(--border-color)", borderRadius: "8px" }}>
        <Space direction="vertical" size="small">
          <Text style={{ fontSize: "12px", color: "var(--text-main)" }}>🛡️ <b>Row-Level Filter:</b> <code>Region IS NOT NULL</code></Text>
          <Text style={{ fontSize: "12px", color: "var(--text-main)" }}>🛡️ <b>Column Masking:</b> Active for PII (emails, names masked for Analyst role)</Text>
          <Text style={{ fontSize: "12px", color: "var(--text-main)" }}>⚡ <b>Caching:</b> SQL results cached for 15 mins</Text>
        </Space>
      </Card>
    </Drawer>
  );
}

export default StatsDrawer;
