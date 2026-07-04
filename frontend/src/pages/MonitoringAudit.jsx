import React, { useState, useEffect } from "react";
import { 
  Table, Card, Typography, Tag, Space, Button, Drawer, Badge, 
  Input, Select, Row, Col, Divider, Alert 
} from "antd";
import { 
  SearchOutlined, EyeOutlined, FileTextOutlined, ReloadOutlined, 
  LockOutlined, BugOutlined 
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

export default function MonitoringAudit({ API, token }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedLog, setSelectedLog] = useState(null);
  
  const [searchUser, setSearchUser] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [actionFilter, setActionFilter] = useState("ALL");

  const loadLogs = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/query-history`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        // Translate history records to audit logs structure
        const formattedLogs = data.map(item => ({
          id: item.id,
          user_id: item.employee_id || "analyst_east",
          action_type: item.execution_status === "CLS_BLOCKED" ? "CLS_VIOLATION" : "SQL_EXECUTION",
          resource: "sales_trans",
          query_text: item.question,
          generated_sql: item.sql_query,
          status: item.execution_status === "SUCCESS" ? "SUCCESS" : "FAILED",
          ip_address: "192.168.1.144",
          execution_time: item.execution_time,
          created_at: item.created_at
        }));
        setLogs(formattedLogs);
      } else {
        throw new Error();
      }
    } catch (err) {
      // Mock logs for offline/standalone execution
      setLogs([
        {
          id: 1001,
          user_id: "EMP1002",
          action_type: "SQL_EXECUTION",
          resource: "sales_trans",
          query_text: "What were our total sales in Region East yesterday?",
          generated_sql: "SELECT SUM(sales_amount) FROM sales_trans WHERE region = 'East' AND transaction_date >= DATEADD(day, -1, GETDATE())",
          status: "SUCCESS",
          ip_address: "10.20.14.88",
          execution_time: 1.15,
          created_at: "2026-06-15T12:02:11Z"
        },
        {
          id: 1002,
          user_id: "EMP1002",
          action_type: "CLS_VIOLATION",
          resource: "customers",
          query_text: "Show customer emails for VIP tier",
          generated_sql: "SELECT customer_name, email FROM customers WHERE tier = 'VIP'",
          status: "BLOCKED",
          ip_address: "10.20.14.88",
          execution_time: 0.05,
          created_at: "2026-06-15T11:58:05Z"
        },
        {
          id: 1003,
          user_id: "EMP1003",
          action_type: "SQL_EXECUTION",
          resource: "products",
          query_text: "List items with unit price over 100",
          generated_sql: "SELECT product_name, unit_price FROM products WHERE unit_price > 100",
          status: "SUCCESS",
          ip_address: "10.20.14.90",
          execution_time: 0.82,
          created_at: "2026-06-15T11:40:42Z"
        },
        {
          id: 1004,
          user_id: "EMP1002",
          action_type: "RLS_INJECTION",
          resource: "sales_trans",
          query_text: "Get sales transactions and customer ids",
          generated_sql: "SELECT transaction_id, customer_id, sales_amount FROM sales_trans WHERE region = 'East'",
          status: "SUCCESS",
          ip_address: "10.20.14.88",
          execution_time: 1.05,
          created_at: "2026-06-15T11:35:10Z"
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [token, API]); // eslint-disable-line

  const handleOpenDrawer = (record) => {
    setSelectedLog(record);
    setDrawerVisible(true);
  };

  const columns = [
    {
      title: "Timestamp",
      dataIndex: "created_at",
      key: "created_at",
      render: (text) => <span style={{ color: "#6b7280", fontSize: "12px" }}>{new Date(text).toLocaleString()}</span>
    },
    {
      title: "User ID",
      dataIndex: "user_id",
      key: "user_id",
      render: (text) => <span style={{ fontFamily: "monospace", color: "var(--text-main)" }}>{text}</span>
    },
    {
      title: "Action Type",
      dataIndex: "action_type",
      key: "action_type",
      render: (text) => {
        let color = "blue";
        if (text.includes("VIOLATION")) color = "error";
        if (text.includes("INJECTION")) color = "purple";
        return <Tag color={color} bordered={false} style={{ fontSize: "10px" }}>{text}</Tag>;
      }
    },
    {
      title: "Natural Question",
      dataIndex: "query_text",
      key: "query_text",
      ellipsis: true,
      render: (text) => <span style={{ color: "#e5e7eb" }}>"{text}"</span>
    },
    {
      title: "Response Latency",
      dataIndex: "execution_time",
      key: "execution_time",
      render: (sec) => sec ? <span style={{ color: "var(--code-blue)" }}>{sec.toFixed(2)}s</span> : <span style={{ color: "#6b7280" }}>-</span>
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status) => {
        let statusBadge = "success";
        if (status === "BLOCKED") statusBadge = "warning";
        if (status === "FAILED") statusBadge = "error";
        return <Badge status={statusBadge} text={<span style={{ color: "var(--text-secondary)" }}>{status}</span>} />;
      }
    },
    {
      title: "Trace Details",
      key: "action",
      render: (_, record) => (
        <Button 
          type="text" 
          icon={<EyeOutlined />} 
          style={{ color: "var(--code-blue)" }} 
          onClick={() => handleOpenDrawer(record)}
        />
      )
    }
  ];

  const filteredLogs = logs.filter(log => {
    const matchesUser = log.user_id.toLowerCase().includes(searchUser.toLowerCase()) || 
                        log.query_text.toLowerCase().includes(searchUser.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || log.status === statusFilter;
    const matchesAction = actionFilter === "ALL" || log.action_type === actionFilter;
    return matchesUser && matchesStatus && matchesAction;
  });

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            Platform Audits & Logs
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Track and audit database transactions, policy triggers, authentication failures, and CLS violations.
          </Text>
        </div>
        <Button 
          icon={<ReloadOutlined />} 
          onClick={loadLogs}
          style={{ background: "var(--border-color)", border: "1px solid var(--border-light)", color: "var(--text-main)" }}
        >
          Reload Logs
        </Button>
      </div>

      {/* Filter Options */}
      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px", marginBottom: "16px" }}>
        <Row gutter={16}>
          <Col span={8}>
            <Input 
              prefix={<SearchOutlined style={{ color: "#6b7280" }} />} 
              placeholder="Search user or question..." 
              value={searchUser}
              onChange={e => setSearchUser(e.target.value)}
              style={{ background: "var(--border-color)", border: "1px solid var(--border-light)" }}
            />
          </Col>
          <Col span={8}>
            <Select 
              value={statusFilter} 
              onChange={setStatusFilter} 
              style={{ width: "100%" }}
            >
              <Option value="ALL">All Statuses</Option>
              <Option value="SUCCESS">SUCCESS</Option>
              <Option value="BLOCKED">BLOCKED</Option>
              <Option value="FAILED">FAILED</Option>
            </Select>
          </Col>
          <Col span={8}>
            <Select 
              value={actionFilter} 
              onChange={setActionFilter} 
              style={{ width: "100%" }}
            >
              <Option value="ALL">All Actions</Option>
              <Option value="SQL_EXECUTION">SQL_EXECUTION</Option>
              <Option value="CLS_VIOLATION">CLS_VIOLATION</Option>
              <Option value="RLS_INJECTION">RLS_INJECTION</Option>
            </Select>
          </Col>
        </Row>
      </Card>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Table 
          dataSource={filteredLogs} 
          columns={columns} 
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          style={{ background: "var(--bg-card)" }}
          className="dark-table"
        />
      </Card>

      {/* Detailed Log Drawer */}
      <Drawer
        title={
          <Space>
            <LockOutlined style={{ color: "#6366f1" }} />
            <span style={{ color: "var(--text-main)" }}>Audit Log Trace [#{selectedLog?.id}]</span>
          </Space>
        }
        placement="right"
        width={650}
        onClose={() => setDrawerVisible(false)}
        open={drawerVisible}
        styles={{ 
          body: { backgroundColor: "var(--bg-card)", color: "var(--text-secondary)" },
          header: { backgroundColor: "var(--border-color)", borderBottom: "1px solid var(--border-light)" }
        }}
      >
        {selectedLog && (
          <div>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Text type="secondary" style={{ display: "block" }}>Timestamp</Text>
                <Text style={{ color: "var(--text-main)" }}>{new Date(selectedLog.created_at).toUTCString()}</Text>
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ display: "block" }}>IP Address</Text>
                <Text style={{ color: "var(--text-main)" }}>{selectedLog.ip_address}</Text>
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ display: "block" }}>User Account ID</Text>
                <Text style={{ color: "var(--text-main)", fontFamily: "monospace" }}>{selectedLog.user_id}</Text>
              </Col>
              <Col span={12}>
                <Text type="secondary" style={{ display: "block" }}>Target DB Table</Text>
                <Tag color="geekblue">{selectedLog.resource}</Tag>
              </Col>
            </Row>

            <Divider style={{ borderColor: "var(--border-color)", margin: "16px 0" }} />

            <div style={{ marginBottom: "16px" }}>
              <Text type="secondary" style={{ display: "block", marginBottom: "4px" }}>Natural Language Input</Text>
              <Paragraph style={{ color: "var(--text-main)", fontStyle: "italic" }}>
                "{selectedLog.query_text}"
              </Paragraph>
            </div>

            {selectedLog.action_type === "CLS_VIOLATION" ? (
              <Alert 
                message="Security Policy Triggered" 
                description="This request was intercepted by the Column-Level Security (CLS) check. Access was blocked prior to SQL command execution because it contained blocked fields."
                type="warning" 
                showIcon 
                icon={<BugOutlined />}
                style={{ background: "#451a03", border: "1px solid #b45309", color: "#fef3c7", marginBottom: "16px" }}
              />
            ) : null}

            <div>
              <Text type="secondary" style={{ display: "block", marginBottom: "4px" }}>Generated SQL Command</Text>
              <pre style={{ 
                background: "var(--bg-layout)", 
                padding: "16px", 
                borderRadius: "8px", 
                color: "var(--text-active)", 
                fontFamily: "monospace", 
                fontSize: "12px",
                whiteSpace: "pre-wrap",
                border: "1px solid var(--border-color)"
              }}>
                {selectedLog.generated_sql}
              </pre>
            </div>

            <Divider style={{ borderColor: "var(--border-color)", margin: "16px 0" }} />

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "13px" }}>
              <Text type="secondary">Action Result Status:</Text>
              <Tag color={selectedLog.status === "SUCCESS" ? "success" : "error"}>{selectedLog.status}</Tag>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
