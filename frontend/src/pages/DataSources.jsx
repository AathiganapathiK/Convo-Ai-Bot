import React, { useState, useEffect } from "react";
import { 
  Table, Card, Button, Tag, Space, Typography, Modal, Form, 
  Input, InputNumber, Select, Tooltip, Badge, Divider, Drawer,
  Row, Col
} from "antd";
import { message } from "../utils/message";
import { 
  PlusOutlined, DatabaseOutlined, PlayCircleOutlined, DeleteOutlined, 
  CheckCircleOutlined, ExclamationCircleOutlined, SyncOutlined 
} from "@ant-design/icons";
import DeleteDatasourceModal from "../components/DeleteDatasourceModal";

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

export default function DataSources({ API, token }) {
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [testLoading, setTestLoading] = useState({});
  const [form] = Form.useForm();

  // Delete Datasource Workflow State
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [selectedDatasourceId, setSelectedDatasourceId] = useState(null);
  const [deleteSummary, setDeleteSummary] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(null);
  const [confirmText, setConfirmText] = useState("");

  const fetchConnections = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/connections`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setConnections(data);
      } else {
        message.error("Failed to load database connections");
      }
    } catch (err) {
      console.error(err);
      // Fallback mockup for standalone testing
      setConnections([
        {
          connection_id: "conn_01",
          connection_name: "dw-production-retail",
          database_type: "sqlserver",
          host: "10.200.4.15",
          port: 1433,
          database_name: "online_retail_dw",
          username: "ai_read_only",
          is_active: true,
          last_tested_at: "2026-06-15T11:30:00",
          last_sync_at: "2026-06-15T09:00:00",
          created_at: "2026-06-01T08:00:00"
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConnections();
  }, [token, API]); // eslint-disable-line

  const openDeleteModal = async (record) => {
    setSelectedDatasourceId(record.connection_id);
    setDeleteSummary(null);
    setConfirmText("");
    setSummaryError(null);
    setDeleteModalOpen(true);

    try {
      const res = await fetch(`${API}/connections/${record.connection_id}/delete-summary`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setDeleteSummary(data);
      } else {
        const errorData = await res.json().catch(() => ({}));
        setSummaryError(errorData.message || "Failed to load delete summary. Please try again.");
      }
    } catch (err) {
      console.error(err);
      setSummaryError("Network error while loading summary.");
    }
  };

  const handleDeleteDatasource = async () => {
    if (!selectedDatasourceId) return;
    setDeleteLoading(true);
    try {
      const res = await fetch(`${API}/connections/${selectedDatasourceId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        message.success("Datasource deleted successfully.");
        setDeleteModalOpen(false);
        setConfirmText("");
        setDeleteSummary(null);
        setSelectedDatasourceId(null);
        fetchConnections();
      } else {
        const errData = await res.json().catch(() => ({}));
        message.error(errData.message || "Failed to delete datasource.");
      }
    } catch (err) {
      console.error(err);
      message.error("Error connecting to server to delete datasource.");
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleTestConnection = async (record) => {
    console.log(record);
    const connId = record.connection_id;

    setTestLoading(prev => ({
      ...prev,
      [connId]: true
    }));

    try {
      const response = await fetch(
        `${API}/connections/${record.connection_id}/test`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      const result = await response.json();

      if (response.ok && result.success) {
        message.success(result.message);

        setConnections(prev =>
          prev.map(c =>
            c.connection_id === connId
              ? {
                  ...c,
                  last_tested_at: new Date().toISOString()
                }
              : c
          )
        );
      } else {
        message.error(result.message || "Connection test failed");
      }
    } catch (err) {
      console.error(err);
      message.error("Unable to connect to the server");
    } finally {
      setTestLoading(prev => ({
        ...prev,
        [connId]: false
      }));
    }
  };

  const handleDisableConnection = async (record) => {
    try {
      const res = await fetch(`${API}/connections/${record.connection_id}/disable`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        message.success(`Connection "${record.connection_name}" disabled`);
        fetchConnections();
      } else {
        // Mock disable locally
        setConnections(prev => prev.map(c => 
          c.connection_id === record.connection_id 
            ? { ...c, is_active: false } 
            : c
        ));
        message.success(`Connection "${record.connection_name}" disabled (Local mode)`);
      }
    } catch (err) {
      console.error(err);
      message.error("Failed to disable connection");
    }
  };

  const onFinish = async (values) => {
    try {
      const res = await fetch(`${API}/connections`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(values)
      });
      if (res.ok) {
        message.success("Database connection registered successfully");
        setIsModalVisible(false);
        form.resetFields();
        fetchConnections();
      } else {
        // Local simulation add
        const newConn = {
          connection_id: "conn_" + Math.random().toString(36).substr(2, 9),
          connection_name: values.connection_name,
          database_type: values.database_type,
          host: values.host,
          port: values.port || 1433,
          database_name: values.database_name,
          username: values.username || "admin",
          is_active: true,
          last_tested_at: null,
          last_sync_at: null,
          created_at: new Date().toISOString()
        };
        setConnections(prev => [...prev, newConn]);
        message.success("Database connection added (Local mode)");
        setIsModalVisible(false);
        form.resetFields();
      }
    } catch (err) {
      console.error(err);
      message.error("Error creating connection");
    }
  };

  const columns = [
    {
      title: "Connection Name",
      dataIndex: "connection_name",
      key: "connection_name",
      render: (text, record) => (
        <Space>
          <DatabaseOutlined style={{ color: "#6366f1", fontSize: "16px" }} />
          <span style={{ fontWeight: 600, color: "var(--text-main)" }}>{text}</span>
          {!record.is_active && <Tag color="default">Disabled</Tag>}
        </Space>
      )
    },
    {
      title: "Type",
      dataIndex: "database_type",
      key: "database_type",
      render: (text) => (
        <Tag color="geekblue" style={{ textTransform: "uppercase" }}>{text}</Tag>
      )
    },
    {
      title: "Host / Endpoint",
      dataIndex: "host",
      key: "host",
      render: (text, record) => (
        <span style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
          {text}:{record.port || 1433}
        </span>
      )
    },
    {
      title: "Database Name",
      dataIndex: "database_name",
      key: "database_name",
      render: (text) => <code style={{ color: "var(--code-purple)" }}>{text}</code>
    },
    {
      title: "Sync Status",
      dataIndex: "is_active",
      key: "sync_status",
      render: (isActive, record) => (
        <Space direction="vertical" size={2}>
          <Badge 
            status={isActive ? "success" : "default"} 
            text={<span style={{ color: isActive ? "var(--text-active)" : "var(--text-muted)" }}>{isActive ? "Online" : "Offline"}</span>} 
          />
          {record.last_sync_at && (
            <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>
              Sync: {new Date(record.last_sync_at).toLocaleDateString()}
            </span>
          )}
        </Space>
      )
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space size="middle">
          <Button 
            type="text" 
            icon={<PlayCircleOutlined />} 
            onClick={() => handleTestConnection(record)} 
            loading={testLoading[record.connection_id]}
            style={{ color: "var(--code-blue)" }}
          >
            Test
          </Button>
          <Divider type="vertical" style={{ borderColor: "var(--border-light)" }} />
          {record.is_active ? (
            <Button 
              type="text" 
              danger 
              icon={<DeleteOutlined />} 
              onClick={() => handleDisableConnection(record)}
            >
              Disable
            </Button>
          ) : (
            <Button 
              type="text" 
              style={{ color: "#10b981" }}
              onClick={async () => {
                try {
                  const res = await fetch(`${API}/connections/${record.connection_id}/enable`, {
                    method: "PUT",
                    headers: { Authorization: `Bearer ${token}` }
                  });
                  if (res.ok) {
                    message.success(`Connection "${record.connection_name}" enabled`);
                    fetchConnections();
                  } else {
                    message.error("Failed to enable connection");
                  }
                } catch (err) {
                  console.error(err);
                  message.error("Failed to enable connection");
                }
              }}
            >
              Enable
            </Button>
          )}
          <Divider type="vertical" style={{ borderColor: "var(--border-light)" }} />
          <Button 
            type="text" 
            danger 
            icon={<DeleteOutlined />} 
            onClick={() => openDeleteModal(record)}
          >
            Delete
          </Button>
        </Space>
      )
    }
  ];

  return (
    <div style={{ padding: "4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <Title level={3} style={{ color: "var(--text-main)", margin: 0, fontWeight: 700 }}>
            Data Sources
          </Title>
          <Text style={{ color: "var(--text-muted)" }}>
            Register database credentials, test connectivity endpoints, and trigger metadata schema synchronizations.
          </Text>
        </div>
        <Button 
          type="primary" 
          icon={<PlusOutlined />}
          style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}
          onClick={() => setIsModalVisible(true)}
        >
          Add Connection
        </Button>
      </div>

      <Card bordered={false} style={{ background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "12px" }}>
        <Table 
          dataSource={connections} 
          columns={columns} 
          loading={loading}
          rowKey="connection_id"
          pagination={false}
          style={{ background: "var(--bg-card)" }}
          className="dark-table"
        />
      </Card>

      {/* Add Connection Modal */}
      <Modal
        title={<span style={{ color: "var(--text-main)" }}>Register Database Connection</span>}
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={null}
        style={{ top: 50 }}
        styles={{ body: { backgroundColor: "var(--bg-card)", padding: "16px 24px" } }}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={{ database_type: "sqlserver", port: 1433 }}
        >
          <Form.Item
            name="connection_name"
            label={<span style={{ color: "var(--text-secondary)" }}>Connection Label</span>}
            rules={[{ required: true, message: "Please input connection name!" }]}
          >
            <Input placeholder="e.g. retail-datawarehouse-prod" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="database_type"
                label={<span style={{ color: "var(--text-secondary)" }}>Database Provider</span>}
                rules={[{ required: true }]}
              >
                <Select style={{ width: "100%" }}>
                  <Option value="sqlserver">Microsoft SQL Server</Option>
                  <Option value="postgres">PostgreSQL</Option>
                  <Option value="mysql">MySQL</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="database_name"
                label={<span style={{ color: "var(--text-secondary)" }}>Database Name</span>}
                rules={[{ required: true }]}
              >
                <Input placeholder="e.g. SalesData" />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={16}>
              <Form.Item
                name="host"
                label={<span style={{ color: "var(--text-secondary)" }}>Host Endpoint</span>}
                rules={[{ required: true }]}
              >
                <Input placeholder="e.g. 192.168.1.100 or dw.acme.com" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="port"
                label={<span style={{ color: "var(--text-secondary)" }}>Port</span>}
              >
                <InputNumber style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="username"
                label={<span style={{ color: "var(--text-secondary)" }}>Username</span>}
              >
                <Input placeholder="read-only-user" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="password"
                label={<span style={{ color: "var(--text-secondary)" }}>Password</span>}
              >
                <Input.Password placeholder="••••••••" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="connection_string"
            label={<span style={{ color: "var(--text-secondary)" }}>Direct Connection String (Optional)</span>}
          >
            <Input.TextArea placeholder="Driver={ODBC Driver 17 for SQL Server};Server=..." rows={2} />
          </Form.Item>

          <Divider style={{ borderColor: "var(--border-color)", margin: "16px 0" }} />

          <Form.Item style={{ margin: 0, textAlign: "right" }}>
            <Space>
              <Button onClick={() => setIsModalVisible(false)}>
                Cancel
              </Button>
              <Button type="primary" htmlType="submit" style={{ backgroundColor: "#4f46e5", borderColor: "#4338ca" }}>
                Add DataSource
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Enterprise Delete Datasource Modal */}
      <DeleteDatasourceModal
        open={deleteModalOpen}
        loading={deleteLoading}
        deleteSummary={deleteSummary}
        summaryError={summaryError}
        confirmText={confirmText}
        setConfirmText={setConfirmText}
        onDelete={handleDeleteDatasource}
        onCancel={() => {
          setDeleteModalOpen(false);
          setConfirmText("");
        }}
      />
    </div>
  );
}
